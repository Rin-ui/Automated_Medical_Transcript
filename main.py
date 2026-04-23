from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from faster_whisper import WhisperModel
import requests
import sqlite3
from datetime import datetime
from pathlib import Path
import os

# ==================================================
# CONFIG
# ==================================================

app = FastAPI(title="Doctor Voice AI")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Free local Whisper model
model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

# ==================================================
# DATABASE
# ==================================================

DB_FILE = "hospital.db"

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
DROP TABLE IF EXISTS reports
""")

cursor.execute("""
CREATE TABLE reports(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    doctor_name TEXT,
    transcription TEXT,
    symptoms TEXT,
    medicines TEXT,
    prescription TEXT,
    created_at TEXT
)
""")

conn.commit()

# ==================================================
# HOME PAGE
# ==================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>Doctor Voice AI</title>

<style>
body{
    background:#081225;
    color:white;
    font-family:Arial;
    padding:40px;
}
.box{
    max-width:760px;
    margin:auto;
    background:#111827;
    padding:35px;
    border-radius:22px;
}
input{
    width:100%;
    padding:14px;
    margin:10px 0;
    border:none;
    border-radius:12px;
    font-size:16px;
}
button{
    padding:12px 20px;
    margin:10px 5px;
    border:none;
    border-radius:12px;
    cursor:pointer;
    font-size:16px;
}
.start{background:#2563eb;color:white;}
.stop{background:#dc2626;color:white;}
.upload{background:#16a34a;color:white;}

.status{
    margin-top:15px;
    color:#60a5fa;
    font-size:18px;
}
.timer{
    font-size:28px;
    margin-top:10px;
    color:#93c5fd;
    font-weight:bold;
}
canvas{
    width:100%;
    height:90px;
    background:#0b1220;
    border-radius:12px;
    margin-top:15px;
}
</style>
</head>

<body>

<div class="box">

<h1>🎤 Doctor Live Voice Prescription</h1>

<input type="text" id="patient_name" placeholder="Patient Name">
<input type="text" id="doctor_name" placeholder="Doctor Name">

<button class="start" onclick="startRecording()">🎤 Start</button>
<button class="stop" onclick="stopRecording()">⏹ Stop</button>
<button class="upload" onclick="uploadAudio()">✅ Upload</button>

<div class="status" id="status">Ready</div>
<div class="timer" id="timer">00:00</div>

<canvas id="visualizer"></canvas>

</div>

<script>

let mediaRecorder;
let audioChunks = [];
let stream = null;

let seconds = 0;
let timerInterval = null;

let audioContext;
let analyser;
let dataArray;
let animationId;

function startTimer(){
    seconds = 0;
    clearInterval(timerInterval);

    timerInterval = setInterval(()=>{
        seconds++;

        let min = String(Math.floor(seconds/60)).padStart(2,'0');
        let sec = String(seconds%60).padStart(2,'0');

        document.getElementById("timer").innerText = min + ":" + sec;
    },1000);
}

function stopTimer(){
    clearInterval(timerInterval);
}

function startVisualizer(stream){

    const canvas = document.getElementById("visualizer");
    const ctx = canvas.getContext("2d");

    canvas.width = canvas.offsetWidth;
    canvas.height = 90;

    audioContext = new AudioContext();
    analyser = audioContext.createAnalyser();

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    analyser.fftSize = 128;

    const bufferLength = analyser.frequencyBinCount;
    dataArray = new Uint8Array(bufferLength);

    function draw(){

        animationId = requestAnimationFrame(draw);

        analyser.getByteFrequencyData(dataArray);

        ctx.fillStyle = "#0b1220";
        ctx.fillRect(0,0,canvas.width,canvas.height);

        let barWidth = (canvas.width / bufferLength) * 1.5;
        let x = 0;

        for(let i=0;i<bufferLength;i++){

            let barHeight = Math.max(dataArray[i],2);

            ctx.fillStyle = "rgb(59,130,246)";
            ctx.fillRect(
                x,
                canvas.height-barHeight,
                barWidth,
                barHeight
            );

            x += barWidth + 2;
        }
    }

    draw();
}

function stopVisualizer(){

    cancelAnimationFrame(animationId);

    if(audioContext){
        audioContext.close();
    }
}

async function startRecording(){

    try{

        stream = await navigator.mediaDevices.getUserMedia({audio:true});

        audioChunks = [];

        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = e=>{
            if(e.data.size > 0){
                audioChunks.push(e.data);
            }
        };

        mediaRecorder.start();

        document.getElementById("status").innerText = "🎙 Recording...";
        startTimer();
        startVisualizer(stream);

    }catch(err){
        alert("Microphone permission denied.");
    }
}

function stopRecording(){

    if(mediaRecorder && mediaRecorder.state !== "inactive"){
        mediaRecorder.stop();
    }

    if(stream){
        stream.getTracks().forEach(track => track.stop());
    }

    stopTimer();
    stopVisualizer();

    document.getElementById("status").innerText = "⏹ Recording Stopped";
}

async function uploadAudio(){

    if(audioChunks.length === 0){
        alert("Please record first.");
        return;
    }

    const patient = document.getElementById("patient_name").value.trim();
    const doctor = document.getElementById("doctor_name").value.trim();

    if(!patient || !doctor){
        alert("Enter names first.");
        return;
    }

    const blob = new Blob(audioChunks,{type:"audio/webm"});

    let formData = new FormData();
    formData.append("patient_name", patient);
    formData.append("doctor_name", doctor);
    formData.append("audio_file", blob, "recording.webm");

    document.getElementById("status").innerText = "⬆ Uploading...";

    const response = await fetch("/upload",{
        method:"POST",
        body:formData
    });

    const html = await response.text();

    document.open();
    document.write(html);
    document.close();
}

</script>

</body>
</html>
"""

# ==================================================
# UPLOAD
# ==================================================

@app.post("/upload", response_class=HTMLResponse)
async def upload(
    patient_name: str = Form(...),
    doctor_name: str = Form(...),
    audio_file: UploadFile = File(...)
):

    try:
        filepath = UPLOAD_DIR / f"{datetime.now().timestamp()}_{audio_file.filename}"

        with open(filepath, "wb") as f:
            f.write(await audio_file.read())

        # ==========================================
        # WHISPER
        # ==========================================

        segments, info = model.transcribe(str(filepath))

        raw_text = " ".join(
            [segment.text for segment in segments]
        ).strip()

        # ==========================================
        # GEMMA 2B AI
        # ==========================================

        prompt = f"""
You are a professional medical assistant.

Doctor Dictation:
{raw_text}

Return clearly in this format:

1. Symptoms:
2. Medicines:
3. Prescription:
"""

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model":"gemma:2b",
                "prompt":prompt,
                "stream":False
            },
            timeout=120
        )

        data = response.json()
        prescription = data.get("response", "No response generated.")

        # ==========================================
        # SAVE DATABASE
        # ==========================================

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        cursor.execute("""
        INSERT INTO reports(
            patient_name,
            doctor_name,
            transcription,
            symptoms,
            medicines,
            prescription,
            created_at
        )
        VALUES(?,?,?,?,?,?,?)
        """,(
            patient_name,
            doctor_name,
            raw_text,
            "",
            "",
            prescription,
            now
        ))

        conn.commit()

        return f"""
<html>
<body style="background:#081225;color:white;font-family:Arial;padding:40px;">

<h1>✅ AI Medical Report Generated</h1>

<p><b>Patient:</b> {patient_name}</p>
<p><b>Doctor:</b> {doctor_name}</p>

<h2>🎙 Raw Transcription</h2>
<div style="background:#111827;padding:20px;border-radius:15px;">
{raw_text}
</div>

<br>

<h2>🩺 AI Prescription Format</h2>
<div style="background:#111827;padding:20px;border-radius:15px;white-space:pre-wrap;">
{prescription}
</div>

<br><br>
<a href="/" style="color:#60a5fa;">⬅ Back</a>

</body>
</html>
"""

    except Exception as e:

        return f"""
<html>
<body style="background:#081225;color:white;font-family:Arial;padding:40px;">

<h1>❌ Internal Server Error</h1>

<div style="background:#111827;padding:20px;border-radius:15px;">
{str(e)}
</div>

<br><br>

<a href="/" style="color:#60a5fa;">⬅ Back</a>

</body>
</html>
"""

# ==================================================
# RUN
# ollama pull gemma:2b
# ollama run gemma:2b
# uvicorn main:app --reload
# ==================================================
