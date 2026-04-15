import os
import uuid
import threading
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import HTMLResponse, JSONResponse
from starlette.requests import Request
import uvicorn

load_dotenv()

# In-memory store: run_id -> {status, result, error}
run_registry: dict = {}


def execute_run(run_id: str, task_description: str):
    """Runs the crew in a background thread."""
    try:
        from my_autonomous_agent.crew import MyAutonomousAgent
        result = MyAutonomousAgent().crew().kickoff(inputs={"task_description": task_description})
        run_registry[run_id] = {
            "status": "completed",
            "result": str(result),
            "error": None,
        }
    except Exception as e:
        run_registry[run_id] = {
            "status": "failed",
            "result": None,
            "error": str(e),
        }


async def homepage(request: Request):
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Agent</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }

        h1 {
            font-size: 1.8rem;
            font-weight: 600;
            margin-bottom: 8px;
            color: #ffffff;
        }

        .subtitle {
            color: #888;
            margin-bottom: 40px;
            font-size: 0.95rem;
        }

        .card {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 28px;
            width: 100%;
            max-width: 700px;
            margin-bottom: 24px;
        }

        label {
            display: block;
            font-size: 0.85rem;
            color: #aaa;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        textarea {
            width: 100%;
            background: #111;
            border: 1px solid #333;
            border-radius: 8px;
            color: #e0e0e0;
            font-size: 0.95rem;
            padding: 14px;
            resize: vertical;
            min-height: 120px;
            outline: none;
            transition: border-color 0.2s;
            font-family: inherit;
        }

        textarea:focus { border-color: #555; }

        .examples {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }

        .example-chip {
            background: #222;
            border: 1px solid #333;
            border-radius: 20px;
            padding: 5px 14px;
            font-size: 0.8rem;
            color: #aaa;
            cursor: pointer;
            transition: all 0.2s;
        }

        .example-chip:hover {
            background: #2a2a2a;
            border-color: #555;
            color: #ddd;
        }

        button[type=submit] {
            margin-top: 20px;
            width: 100%;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 14px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }

        button[type=submit]:hover { background: #1d4ed8; }
        button[type=submit]:disabled { background: #333; color: #666; cursor: not-allowed; }

        #status-card { display: none; }

        .status-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
        }

        .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #888;
        }

        .dot.running { background: #f59e0b; animation: pulse 1.2s infinite; }
        .dot.completed { background: #22c55e; }
        .dot.failed { background: #ef4444; }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        #status-text { font-weight: 500; }

        #result-box {
            background: #111;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 16px;
            font-size: 0.88rem;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            overflow-y: auto;
            color: #ccc;
        }

        .run-id {
            font-size: 0.75rem;
            color: #555;
            margin-top: 12px;
        }
    </style>
</head>
<body>
    <h1>Autonomous Agent</h1>
    <p class="subtitle">Describe your task — the agent will research, analyze, and save results.</p>

    <div class="card">
        <form id="task-form">
            <label for="task">Task Description</label>
            <textarea
                id="task"
                name="task"
                placeholder="e.g. Find the current price of Bitcoin, calculate how much $1000 would buy, and save to crypto_report.txt"
            ></textarea>

            <div class="examples">
                <span class="example-chip" onclick="setExample(this)">Bitcoin price report</span>
                <span class="example-chip" onclick="setExample(this)">Top 5 AI news today</span>
                <span class="example-chip" onclick="setExample(this)">Python vs JavaScript comparison</span>
                <span class="example-chip" onclick="setExample(this)">Latest breakthroughs in quantum computing</span>
            </div>

            <button type="submit" id="submit-btn">Run Agent</button>
        </form>
    </div>

    <div class="card" id="status-card">
        <div class="status-header">
            <div class="dot" id="status-dot"></div>
            <span id="status-text">Starting...</span>
        </div>
        <div id="result-box">Waiting for agent to start...</div>
        <div class="run-id" id="run-id-label"></div>
    </div>

    <script>
        const examples = {
            "Bitcoin price report": "Find the current price of Bitcoin, calculate how much $1000 would buy, and save this report to a file named 'crypto_report.txt'.",
            "Top 5 AI news today": "Search for the top 5 AI news stories from today and save a summary to 'ai_news.txt'.",
            "Python vs JavaScript comparison": "Research the key differences between Python and JavaScript for backend development and save a comparison report to 'py_vs_js.txt'.",
            "Latest breakthroughs in quantum computing": "Find the latest breakthroughs in quantum computing in 2025 and save a report to 'quantum_report.txt'."
        };

        function setExample(el) {
            document.getElementById('task').value = examples[el.textContent.trim()] || el.textContent;
        }

        let pollInterval = null;

        document.getElementById('task-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const task = document.getElementById('task').value.trim();
            if (!task) return;

            const btn = document.getElementById('submit-btn');
            btn.disabled = true;
            btn.textContent = 'Running...';

            const statusCard = document.getElementById('status-card');
            statusCard.style.display = 'block';
            setStatus('running', 'Agent is working...');
            document.getElementById('result-box').textContent = 'Agent started. This may take 1-3 minutes...';

            const res = await fetch('/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_description: task })
            });
            const data = await res.json();
            const runId = data.run_id;
            document.getElementById('run-id-label').textContent = 'Run ID: ' + runId;

            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => pollStatus(runId, btn), 3000);
        });

        async function pollStatus(runId, btn) {
            const res = await fetch('/status/' + runId);
            const data = await res.json();

            if (data.status === 'completed') {
                clearInterval(pollInterval);
                setStatus('completed', 'Completed');
                document.getElementById('result-box').textContent = data.result || '(no output)';
                btn.disabled = false;
                btn.textContent = 'Run Agent';
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                setStatus('failed', 'Failed');
                document.getElementById('result-box').textContent = 'Error: ' + (data.error || 'Unknown error');
                btn.disabled = false;
                btn.textContent = 'Run Agent';
            }
        }

        function setStatus(state, text) {
            const dot = document.getElementById('status-dot');
            dot.className = 'dot ' + state;
            document.getElementById('status-text').textContent = text;
        }
    </script>
</body>
</html>
"""
    return HTMLResponse(html)


async def run_task(request: Request):
    body = await request.json()
    task_description = body.get("task_description", "").strip()
    if not task_description:
        return JSONResponse({"error": "task_description is required"}, status_code=400)

    run_id = str(uuid.uuid4())
    run_registry[run_id] = {"status": "running", "result": None, "error": None}

    thread = threading.Thread(target=execute_run, args=(run_id, task_description), daemon=True)
    thread.start()

    return JSONResponse({"run_id": run_id, "status": "accepted"})


async def get_status(request: Request):
    run_id = request.path_params["run_id"]
    entry = run_registry.get(run_id)
    if not entry:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return JSONResponse({"run_id": run_id, **entry})


app = Starlette(
    routes=[
        Route("/", homepage),
        Route("/run", run_task, methods=["POST"]),
        Route("/status/{run_id}", get_status),
    ]
)


def serve():
    port = int(os.getenv("UI_PORT", "8000"))
    print(f"Starting Autonomous Agent UI at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
