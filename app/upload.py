from datetime import date, datetime, time, timedelta, timezone as utc_timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select

from db.models import TapEvent
from fastapi.responses import HTMLResponse

from db.database import SessionLocal
from import_members import import_members

app = FastAPI()
MAX_CSV_BYTES = 32 * 1024 * 1024


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!doctype html><html><head><title>Member CSV import</title></head>
    <body><h1>Member CSV import</h1>
    <p><a href="/heatmap">View weekly tap heatmap</a></p>
    <p>Select a CSV with first name, last name, email, and reference tag columns.</p>
    <form id="form"><input id="file" type="file" accept=".csv,text/csv" required>
    <button>Import</button></form><p id="summary" role="status"></p>
    <section id="problems" hidden><h2>Rows needing attention</h2>
    <table><thead><tr><th>Line</th><th>Name</th><th>Reference</th><th>Problem</th></tr></thead>
    <tbody id="issues"></tbody></table></section>
    <script>
    document.getElementById('form').onsubmit = async (event) => {
      event.preventDefault();
      const summary = document.getElementById('summary');
      const section = document.getElementById('problems');
      const issues = document.getElementById('issues');
      summary.textContent = 'Importing...';
      section.hidden = true;
      issues.replaceChildren();
      try {
        const response = await fetch('/import', {method: 'POST', body: document.getElementById('file').files[0]});
        const data = await response.json();
        if (!response.ok) { summary.textContent = data.detail || 'Import failed.'; return; }
        summary.textContent = `${data.updated} updated, ${data.unchanged} unchanged, ${data.issues.length} rows need attention.`;
        for (const issue of data.issues) {
          const row = document.createElement('tr');
          for (const value of [issue.line, issue.name || '—', issue.reference_tag || '—', issue.reason]) {
            const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell);
          }
          issues.appendChild(row);
        }
        section.hidden = data.issues.length === 0;
      } catch (error) { summary.textContent = 'Import failed: ' + error; }
    };
    </script></body></html>"""


@app.post("/import")
async def upload(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_CSV_BYTES:
            raise HTTPException(status_code=413, detail="CSV exceeds 32 MiB")
    try:
        async with SessionLocal() as db:
            return await import_members(db, bytes(data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/heatmap", response_class=HTMLResponse)
async def heatmap():
    return Path(__file__).with_name("heatmap.html").read_text(encoding="utf-8")


@app.get("/api/heatmap")
async def heatmap_data(date: date, timezone: str, bucket_minutes: int = 30):
    if bucket_minutes not in (15, 30, 60):
        raise HTTPException(status_code=400, detail="Bucket size must be 15, 30, or 60 minutes")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid time zone")
    try:
        start_day = date - timedelta(days=date.weekday())
        end_day = start_day + timedelta(days=7)
    except OverflowError:
        raise HTTPException(status_code=400, detail="Date is outside the supported range")
    start = datetime.combine(start_day, time.min, tzinfo=zone).astimezone(utc_timezone.utc)
    end = datetime.combine(end_day, time.min, tzinfo=zone).astimezone(utc_timezone.utc)
    async with SessionLocal() as db:
        result = await db.scalars(select(TapEvent.tapped_at).where(
            TapEvent.tapped_at >= start, TapEvent.tapped_at < end
        ))
        counts = [[0] * (1440 // bucket_minutes) for _ in range(7)]
        for timestamp in result:
            local = timestamp.astimezone(zone)
            counts[(local.date() - start_day).days][(local.hour * 60 + local.minute) // bucket_minutes] += 1
    return {"days": [(start_day + timedelta(days=i)).isoformat() for i in range(7)],
            "counts": counts, "bucket_minutes": bucket_minutes, "total": sum(map(sum, counts))}
