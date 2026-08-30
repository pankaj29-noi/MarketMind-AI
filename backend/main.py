import os
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from charset_normalizer import detect

# Import configurations & helpers
from backend.config import DATABASE_URL
from backend.database.connection import init_db, get_pool, close_pool, get_db_connection
from backend.database.repository import (
    create_session, 
    get_session, 
    save_report, 
    get_reports_by_session, 
    record_execution_metrics,
    get_metrics_summary
)
from backend.services.session_manager import session_manager
from backend.agents.graph import create_agent_graph
from backend.utils.json_sanitizer import sanitize_for_json

# Configure logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Background task to clean up expired sessions
async def session_cleanup_scheduler():
    while True:
        try:
            logger.info("Running session cleanup scheduler...")
            session_manager.clean_expired_sessions()
        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_graph, db_pool
    logger.info("Starting up FastAPI application...")
    
    # 1. Initialize DuckDB Session Manager (logs dynamically inside constructor)
    logger.info("Initializing DuckDB session manager...")
    _ = session_manager
    
    # 2. Initialize application database tables (soft-fail if Postgres is down)
    logger.info("Initializing application database tables...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database init skipped/failed: {e}")
    
    # 3–4. PostgreSQL pool + analytics LangGraph
    # Marketplace demo + Lead Intelligence work with DuckDB alone.
    # Analytics prefers Postgres checkpointer; falls back to in-memory MemorySaver.
    agent_graph = None
    db_pool = None
    try:
        logger.info("Initializing PostgreSQL connection pool...")
        db_pool = get_pool()
    except Exception as e:
        logger.warning(
            "PostgreSQL unavailable — analytics will use in-memory checkpointer; "
            f"marketplace demo and Lead Intelligence still work. Error: {e}"
        )
        db_pool = None

    try:
        logger.info(
            "Compiling LangGraph agent workflow "
            f"({'PostgresSaver' if db_pool is not None else 'MemorySaver'})..."
        )
        agent_graph = create_agent_graph(db_pool)
    except Exception as e:
        logger.error(f"Failed to compile analytics agent with pool={db_pool is not None}: {e}")
        if db_pool is not None:
            try:
                logger.warning("Retrying analytics agent with in-memory MemorySaver...")
                agent_graph = create_agent_graph(None)
            except Exception as e2:
                logger.error(f"MemorySaver analytics agent also failed: {e2}")
                agent_graph = None
        else:
            agent_graph = None

    # 5. Start the background session cleaner
    logger.info("Starting background session cleanup scheduler...")
    cleanup_task = asyncio.create_task(session_cleanup_scheduler())
    
    logger.info("FastAPI backend startup procedures completed.")
    
    yield
    
    # Shutdown procedures
    logger.info("Shutting down FastAPI application...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    close_pool()
    logger.info("FastAPI backend shutdown completed.")

# Initialize FastAPI App with Lifespan
app = FastAPI(
    title="MarketMind AI API",
    description="Agentic B2B Marketplace Intelligence Platform",
    version="1.2",
    lifespan=lifespan,
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for easier portfolio deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temp upload folder
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Global variables for compiled graph and pool
agent_graph = None
db_pool = None

# Background tasks and lifespan context moved to the top of the file
# API Models
class AnalyzeRequest(BaseModel):
    session_id: str
    question: str

# Endpoints
def normalize_encoding(content: bytes) -> bytes:
    """
    Detects the CSV encoding using BOM detection first, then heuristically
    using charset-normalizer with confidence thresholds to avoid false positives,
    and returns standard UTF-8 encoded bytes.
    """
    # 1. BOM Detection first (100% reliable)
    if content.startswith(b'\xef\xbb\xbf'):
        logger.info("BOM detected: UTF-8 with BOM (utf-8-sig)")
        return content.decode('utf-8-sig').encode('utf-8')
    elif content.startswith(b'\xff\xfe') or content.startswith(b'\xfe\xff'):
        logger.info("BOM detected: UTF-16")
        return content.decode('utf-16').encode('utf-8')

    # 2. Heuristic detection with charset_normalizer
    try:
        detection = detect(content)
        encoding = detection.get('encoding')
        confidence = detection.get('confidence') or 0.0
        
        logger.info(f"Detected CSV encoding by charset-normalizer: {encoding} (confidence: {confidence})")
        
        if encoding:
            encoding_lower = encoding.lower()
            
            # Avoid false positive UTF-16/32 detections
            is_utf16_or_32 = 'utf-16' in encoding_lower or 'utf-32' in encoding_lower
            
            if is_utf16_or_32 and confidence < 0.99:
                logger.warning(f"Bypassing low confidence {encoding} detection ({confidence}) to avoid false positives.")
            elif confidence >= 0.7:
                try:
                    decoded = content.decode(encoding)
                    logger.info(f"Successfully normalized CSV encoding from: {encoding}")
                    return decoded.encode('utf-8')
                except Exception as e:
                    logger.warning(f"Failed to decode using detected encoding {encoding}: {e}")
    except Exception as e:
        logger.error(f"Error during charset-normalizer detection: {e}")

    # 3. Deterministic fallbacks if heuristic fails or has low confidence
    # 3a. Try standard UTF-8 (strict)
    try:
        decoded = content.decode('utf-8')
        logger.info("Fallback succeeded: UTF-8")
        return decoded.encode('utf-8')
    except UnicodeDecodeError:
        pass

    # 3b. Try CP1252 (very common Windows encoding)
    try:
        decoded = content.decode('cp1252')
        logger.info("Fallback succeeded: CP1252")
        return decoded.encode('utf-8')
    except UnicodeDecodeError:
        pass

    # 3c. Try Latin-1 / ISO-8859-1 as a final catch-all
    try:
        decoded = content.decode('latin1')
        logger.info("Fallback succeeded: Latin-1")
        return decoded.encode('utf-8')
    except Exception:
        pass

    raise ValueError("Could not determine CSV file encoding with high confidence.")

@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Accepts CSV upload, normalizes character encoding to UTF-8,
    registers it in-memory in Session Manager, creates PostgreSQL session record,
    and returns schema mapping.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
    
    session_id = str(uuid.uuid4())
    dataset_id = f"uploaded_data_{uuid.uuid4().hex[:8]}"
    
    # Save directly to the session's scratch directory
    scratch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scratch", session_id))
    os.makedirs(scratch_dir, exist_ok=True)
    temp_file_path = os.path.join(scratch_dir, f"{dataset_id}.csv")
    
    upload_success = False
    try:
        # Read the file contents
        content_bytes = await file.read()
        
        # Normalize encoding to UTF-8
        try:
            utf8_content = normalize_encoding(content_bytes)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
            
        # Save the normalized UTF-8 file to disk
        with open(temp_file_path, "wb") as buffer:
            buffer.write(utf8_content)
            
        logger.info(f"Saved normalized UTF-8 upload file to scratch: {temp_file_path}")
        
        # Load CSV into session's in-memory DuckDB table
        session_manager.register_csv(session_id, temp_file_path, dataset_id)
        
        # Insert session record into Postgres
        create_session(session_id=session_id, dataset_id=dataset_id, dataset_name=file.filename)
        
        # Retrieve column info/schema
        schema = session_manager.execute_query(
            session_id, 
            f"PRAGMA table_info({dataset_id});"
        )
        columns = [{"name": r["name"], "dtype": r["type"]} for r in schema]
        
        row_count_res = session_manager.execute_query(session_id, f"SELECT COUNT(*) as cnt FROM {dataset_id};")
        row_count = row_count_res[0]["cnt"] if row_count_res else 0
        
        upload_success = True
        return {
            "session_id": session_id,
            "dataset_id": dataset_id,
            "row_count": row_count,
            "columns": columns
        }
        
    except Exception as e:
        logger.error(f"Upload processing failed: {e}")
        # Clean up temp file on failure
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")
    finally:
        # Only clean up on failure
        if not upload_success and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Cleaned up temporary CSV file from disk on upload failure: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")


@app.post("/marketplace/demo")
async def load_marketplace_demo_endpoint():
    """
    Load the packaged MarketMind B2B marketplace demo dataset into a new DuckDB session.
    Registers categories, suppliers, buyers, products, leads, and orders tables.
    """
    from backend.marketplace.demo_data import (
        MARKETPLACE_DATASET_ID,
        MARKETPLACE_DATASET_NAME,
        load_marketplace_demo,
        build_marketplace_schema_profile,
    )

    session_id = str(uuid.uuid4())
    try:
        result = load_marketplace_demo(session_id)
        create_session(
            session_id=session_id,
            dataset_id=MARKETPLACE_DATASET_ID,
            dataset_name=MARKETPLACE_DATASET_NAME,
        )
        # Warm schema profile for faster first analysis
        try:
            build_marketplace_schema_profile(session_id)
        except Exception as schema_err:
            logger.warning(f"Could not pre-build marketplace schema profile: {schema_err}")

        return {
            "session_id": result["session_id"],
            "dataset_id": result["dataset_id"],
            "dataset_name": result["dataset_name"],
            "row_count": result["row_count"],
            "columns": result["columns"],
            "tables": result["tables"],
            "table_stats": result["table_stats"],
            "relationships": [
                r["description"] for r in result.get("relationships", [])
            ],
        }
    except FileNotFoundError as e:
        logger.error(f"Marketplace demo data missing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to load marketplace demo: {e}")
        # Clean up partial DuckDB session
        try:
            session_manager.evict_session(session_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to load marketplace demo: {str(e)}")


class LeadAnalyzeRequest(BaseModel):
    requirement: str
    session_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    run_id: str
    rating: str  # helpful | not_helpful
    comment: Optional[str] = None


@app.post("/marketplace/lead/analyze")
async def analyze_buyer_lead(request: LeadAnalyzeRequest):
    """
    Lead Intelligence: extract a buyer requirement, match marketplace products,
    and return deterministically ranked suppliers via a dedicated LangGraph workflow.
    """
    requirement = (request.requirement or "").strip()
    if not requirement:
        raise HTTPException(status_code=400, detail="requirement must be a non-empty string.")

    from backend.marketplace.lead.matching import ensure_marketplace_session
    from backend.marketplace.lead.graph import run_lead_analysis
    from backend.marketplace.observability import sanitize_error_message

    try:
        session_id = await asyncio.to_thread(
            ensure_marketplace_session, request.session_id
        )
        result = await asyncio.to_thread(run_lead_analysis, session_id, requirement)
        return result
    except ValueError as e:
        # Missing LLM keys etc. — return safe message without crashing
        logger.error(f"Lead analysis configuration error: {e}")
        raise HTTPException(status_code=500, detail=sanitize_error_message(str(e)) or "Configuration error")
    except Exception as e:
        logger.error(f"Lead analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e)) or "Lead analysis failed",
        )


@app.post("/marketplace/feedback")
async def submit_marketplace_feedback(request: FeedbackRequest):
    """Record thumbs up/down feedback for a Lead Intelligence (or other) workflow run."""
    from backend.marketplace.observability import save_workflow_feedback, sanitize_error_message

    run_id = (request.run_id or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required.")

    rating = (request.rating or "").strip().lower()
    if rating not in ("helpful", "not_helpful"):
        raise HTTPException(status_code=400, detail="rating must be 'helpful' or 'not_helpful'.")

    try:
        saved = await asyncio.to_thread(
            save_workflow_feedback,
            run_id,
            rating,
            request.comment,
        )
        return {
            "success": True,
            "feedback": {
                "id": saved.get("id"),
                "run_id": saved.get("run_id"),
                "rating": saved.get("rating"),
                "comment": saved.get("comment"),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Feedback save failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=sanitize_error_message(str(e)) or "Failed to save feedback",
        )


@app.get("/marketplace/observability/runs")
async def get_observability_runs(limit: int = 50):
    """Return recent workflow runs for Agent Monitoring."""
    from backend.marketplace.observability import list_workflow_runs, serialize_run

    try:
        rows = await asyncio.to_thread(list_workflow_runs, limit)
        return {"runs": [serialize_run(r) for r in rows]}
    except Exception as e:
        logger.error(f"Observability runs fetch failed: {e}")
        return {"runs": []}


@app.get("/marketplace/observability/summary")
async def get_observability_summary_endpoint():
    """Aggregate success/latency/feedback metrics for Agent Monitoring."""
    from backend.marketplace.observability import get_observability_summary

    try:
        summary = await asyncio.to_thread(get_observability_summary)
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Observability summary failed: {e}")
        return {
            "summary": {
                "total_runs": 0,
                "complete_count": 0,
                "failure_count": 0,
                "running_count": 0,
                "success_rate": 0.0,
                "average_latency_ms": 0.0,
                "total_feedback": 0,
                "helpful_feedback_count": 0,
                "helpful_feedback_rate": 0.0,
            }
        }


@app.post("/analyze")
async def analyze_data(request: AnalyzeRequest):
    """
    Drives the LangGraph pipeline, assembles and validates the AnalysisResponse,
    persists the report, records metrics, and returns the fully structured JSON.

    The response shape is:
    {
      "success": bool,
      "dataset": { "name", "rows", "columns" },
      "query":   { "question", "execution_time_ms", "execution_id",
                   "provider", "model", "retry_count" },
      "report":  { "title", "executive_summary", "tables", "charts",
                   "insights", "recommendations" },
      "debug":   { "generated_code", "execution_mode", "execution_plan", "llm_reasoning" }
    }
    """
    if agent_graph is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Analytics agent unavailable. Check backend logs. "
                "If PostgreSQL setup failed, restart after fixing DATABASE_URL, "
                "or ensure the MemorySaver fallback compiled successfully."
            ),
        )

    session_id = request.session_id
    question   = request.question

    session_record = get_session(session_id)
    if not session_record:
        # Postgres may be down or session only lives in DuckDB after demo load.
        # Restore from the active in-memory DuckDB session when tables are present.
        duck_session = session_manager.sessions.get(session_id)
        if duck_session and duck_session.registered_tables:
            from backend.marketplace.demo_data import (
                MARKETPLACE_DATASET_ID,
                MARKETPLACE_DATASET_NAME,
                MARKETPLACE_TABLES,
            )
            tables = duck_session.registered_tables
            if all(t in tables for t in MARKETPLACE_TABLES):
                session_record = create_session(
                    session_id=session_id,
                    dataset_id=MARKETPLACE_DATASET_ID,
                    dataset_name=MARKETPLACE_DATASET_NAME,
                )
                logger.info(
                    "Restored marketplace session %s from in-memory DuckDB (Postgres miss).",
                    session_id,
                )
            elif len(tables) == 1:
                tid = tables[0]
                session_record = create_session(
                    session_id=session_id,
                    dataset_id=tid,
                    dataset_name=tid,
                )
                logger.info(
                    "Restored single-table session %s from in-memory DuckDB (Postgres miss).",
                    session_id,
                )

    if not session_record:
        raise HTTPException(status_code=404, detail="Session not found.")

    dataset_id = session_record["dataset_id"]
    config     = {"configurable": {"thread_id": session_id}}

    # Retrieve existing state to preserve schema profile for the same dataset
    existing_schema = {}
    try:
        existing_state = agent_graph.get_state(config)
        if existing_state and isinstance(existing_state.values, dict):
            old_schema = existing_state.values.get("schema_profile")
            if isinstance(old_schema, dict) and old_schema.get("dataset_id") == dataset_id:
                existing_schema = old_schema
    except Exception as e:
        logger.warning(f"Failed to retrieve existing schema state: {e}")

    initial_state = {
        # Session Persistent
        "session_id":        session_id,
        "dataset_id":        dataset_id,
        "duckdb_table":      dataset_id,
        
        # Run-Transient (Inputs & Metadata)
        "schema_profile":    existing_schema,
        "question":          question,
        "resolved_question": None,
        
        # Run-Transient (Execution Plan & Intermediates)
        "plan":              {},
        "generated_code":    "",
        "expected_output_type": "",
        
        # Run-Transient (Outputs)
        "execution_success": False,
        "execution_time_ms": 0.0,
        "output_summary":    {},
        "query_result":      {},
        
        # Run-Transient (Validation & Routing)
        "validation_passed": False,
        "failure_summary":   None,
        "retry_count":       0,
        "retry_target":      "",
        "graceful_failure":  False,
        "retry_history":     [],
        
        # Run-Transient (Visualization)
        "vis_spec":          {},
        "vis_generated_code": "",
        "vis_retry_count":   0,
        "vis_retry_history": [],
        
        # Run-Transient (Final Outputs & Observability)
        "final_report":      {},
        "execution_metadata": [],
        
        # Run-Transient (Phase 2 & 3 Generic State)
        "last_worker_result": {},
        "supervisor_history": [],
        "overall_confidence": 0.0,
        "analysis_artifacts": {},
    }

    logger.info(f"LangGraph execution start — session={session_id}")
    loop_start = asyncio.get_event_loop().time()

    try:
        final_state = await asyncio.to_thread(
            agent_graph.invoke, initial_state, config
        )
        execution_time_ms = (asyncio.get_event_loop().time() - loop_start) * 1000

        # ── Pull structured report from graph state ──────────────────────────
        final_report: dict = final_state.get("final_report") or {}
        success      = final_report.get("success", False)
        retry_count  = final_state.get("retry_count", 0)
        retry_history = final_state.get("retry_history", [])
        pdf_path     = final_report.get("pdf_path")

        # ── Persist to Postgres ──────────────────────────────────────────────
        # Use executive_summary.summary as the stored narrative (backwards-compatible)
        exec_sum   = final_report.get("report", {}).get("executive_summary", {})
        narrative  = exec_sum.get("summary", "Analysis completed.")
        # Extract first chart's plotly_json for legacy chart_plotly_json column
        charts     = final_report.get("report", {}).get("charts", [])
        chart_json = charts[0].get("plotly_json") if charts else None

        saved_report = save_report(
            session_id=session_id,
            question=question,
            narrative_summary=narrative,
            chart_plotly_json=chart_json,
            pdf_file_path=pdf_path,
            execution_time_ms=execution_time_ms,
            success=success,
        )
        execution_id = saved_report.get("id")

        # ── Record metrics ───────────────────────────────────────────────────
        if success:
            success_type = "first_try" if retry_count == 0 else "retry_success"
            failure_type = None
        else:
            success_type = "failed"
            failure_type = (retry_history[-1].get("failure_type") if retry_history else "runtime")
        record_execution_metrics(success_type=success_type, failure_type=failure_type)

        # ── Assemble final response ──────────────────────────────────────────
        dataset_block = final_report.get("dataset", {
            "name":    dataset_id,
            "rows":    0,
            "columns": 0,
        })

        response_body = {
            "success": success,
            "dataset": dataset_block,
            "query": {
                "question":          question,
                "execution_time_ms": round(execution_time_ms, 2),
                "execution_id":      execution_id,
                "provider":          "Groq",
                "model":             "llama-3.3-70b-versatile",
                "retry_count":       retry_count,
            },
            "report": final_report.get("report", {
                "title":             "Analysis Complete",
                "executive_summary": {"headline": "", "summary": narrative, "confidence": "Medium"},
                "tables":            [],
                "charts":            [],
                "insights":          [],
                "recommendations":   [],
            }),
            "debug": final_report.get("debug", {
                "generated_code":  None,
                "execution_mode":  None,
                "execution_plan": None,
                "llm_reasoning":  None,
            }),
        }

        # Sanitize response to prevent JSON serialization crashes on NaNs/Infs
        response_body = sanitize_for_json(response_body)

        return response_body

    except Exception as e:
        logger.error(f"LangGraph execution crashed: {e}")
        record_execution_metrics(success_type="failed", failure_type="runtime")
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")

@app.get("/execution/{session_id}/trace")
async def get_execution_trace(session_id: str):
    """
    Fetches checkpoint state history from the checkpointer and maps raw Pregel steps
    into meaningful pipeline stage runs (schema_profiler, planner, sql_generator,
    sandbox_executor, validator, report_agent) with deduplicated state and combined timing/retry context.
    """
    config = {"configurable": {"thread_id": session_id}}
    try:
        # Query checkpointer history
        history = await asyncio.to_thread(agent_graph.get_state_history, config)
        history_list = list(history)
        if not history_list:
            return {"trace": []}
            
        # Process history in chronological order
        history_chrono = list(reversed(history_list))
        
        # 1. Identify all node runs
        node_runs = []
        for state in history_chrono:
            node_name = None
            if state.tasks:
                node_name = state.tasks[0].name
            elif state.metadata and state.metadata.get("source") != "loop":
                node_name = state.metadata.get("source")
                
            if not node_name or node_name in ("__start__", "__main__", "reflection", "visualization_reflection"):
                continue
                
            # Map code_generator to sql_generator
            if node_name == "code_generator":
                node_name = "sql_generator"
                
            node_runs.append((node_name, state))
            
        # 2. Group by node name to deduplicate while preserving latest states and timing
        stage_states = {}
        stage_durations = {}
        
        for node_name, state in node_runs:
            # Save the latest state for values/status
            stage_states[node_name] = state
            
            # Accumulate duration if available
            duration = 0.0
            if state.metadata and isinstance(state.metadata.get("writes"), dict):
                duration = state.metadata["writes"].get("duration_ms", 250.0)
            else:
                # Check execution_time_ms in state values if this was a sandbox executor node
                if node_name == "sandbox_executor" and isinstance(state.values, dict):
                    duration = state.values.get("execution_time_ms", 250.0)
                else:
                    duration = 250.0
            stage_durations[node_name] = stage_durations.get(node_name, 0.0) + duration
            
        # 3. Get unique ordered stages in order of first appearance
        seen = set()
        ordered_stages = []
        for node_name, _ in node_runs:
            if node_name not in seen:
                seen.add(node_name)
                ordered_stages.append(node_name)
                
        # 4. Build final trace steps for the UI
        trace_steps = []
        for node_name in ordered_stages:
            state = stage_states[node_name]
            checkpoint_id = state.config.get("configurable", {}).get("checkpoint_id") if state.config else None
            values = state.values if isinstance(state.values, dict) else {}
            
            # Construct custom metadata to tell the UI the clean node name and cumulative duration
            metadata = dict(state.metadata) if state.metadata else {}
            metadata["source"] = node_name
            if "writes" not in metadata or not isinstance(metadata["writes"], dict):
                metadata["writes"] = {}
            metadata["writes"]["duration_ms"] = stage_durations[node_name]
            
            trace_steps.append({
                "checkpoint_id": checkpoint_id,
                "values": {
                    "retry_count": values.get("retry_count", 0),
                    "validation_passed": values.get("validation_passed", False),
                    "retry_target": values.get("retry_target"),
                    "graceful_failure": values.get("graceful_failure", False)
                },
                "next_node": state.next,
                "metadata": metadata
            })
            
        logger.info(f"Mapped {len(history_list)} checkpoints to {len(trace_steps)} user-facing pipeline trace stages for session {session_id}.")
        return {"trace": trace_steps}
    except Exception as e:
        logger.error(f"Failed to build custom trace history pipeline for session {session_id}: {e}")
        return {"trace": []}

@app.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """Retrieves all past queries and analyses for a given session."""
    reports = get_reports_by_session(session_id)
    return {"history": reports}

@app.get("/report/{execution_id}/pdf")
async def download_pdf_report(execution_id: int):
    """Serves the generated PDF file using FileResponse."""
    query = "SELECT pdf_file_path FROM reports WHERE id = %s;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (execution_id,))
                row = cur.fetchone()
                
        if not row or not row.get("pdf_file_path") or not os.path.exists(row["pdf_file_path"]):
            raise HTTPException(status_code=404, detail="PDF report not found.")
            
        pdf_path = row["pdf_file_path"]
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            filename=f"analysis_report_{execution_id}.pdf"
        )
    except Exception as e:
        logger.error(f"Error serving PDF: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve PDF.")

@app.get("/metrics")
async def get_metrics():
    """Gets dashboard execution performance metrics."""
    summary = get_metrics_summary()
    return {"metrics": summary}
