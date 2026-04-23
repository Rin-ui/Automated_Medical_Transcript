from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from openai import OpenAI
import sqlite3
import os
from datetime import datetime

# ==========================
# CONFIG
# ==========================

OPENAI_API_KEY = "YOUR_OPENAI_KEY"
client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

os.makedirs("uploads", exist_ok=True)

# ==========================
# DATABASE
# ==========================

conn = sqlite3.connect("hospital.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports(
id INTEGER PRIMARY KEY AUTOINCREMENT,
patient_name TEXT,
doctor_name TEXT,
transcription TEXT,
created_at TEXT
)
""")

conn.commit()

# ==========================
# HOME PAGE
# ==========================

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
.mic{background:#2563eb;color:white;}
.pause{background:#dc2626;color:white;}
.resume{background:#3b82f6;color:white;}
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

audio{
    width:100%;
    margin-top:18px;
}
</style>

</head>
<body>

<div class="box">

<h1>🎤 Doctor Live Voice Prescription</h1>

<form id="uploadForm">

<input type="text" id="patient_name" placeholder="Patient Name" required>
<input type="text" id="doctor_name" placeholder="Doctor Name" required>

<button type="button" class="mic" onclick="startRecording()">🎤 Start</button>
<button type="button" class="pause" onclick="pauseRecording()">⏸ Pause</button>
<button type="button" class="resume" onclick="resumeRecording()">▶ Resume</button>
<button type="button" class="upload" onclick="uploadAudio()">✅ Upload</button>

<div class="status" id="status">Ready</div>
<div class="timer" id="timer">00:00</div>

<canvas id="visualizer"></canvas>

<audio id="audioPlayback" controls></audio>

</form>

</div>

<script>

let mediaRecorder;
let audioChunks = [];
let stream;

let timerInterval;
let seconds = 0;

let audioContext;
let analyser;
let source;
let dataArray;
let animationId;

// =======================
// TIMER
// =======================

function startTimer(){
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

function resetTimer(){
    seconds = 0;
    document.getElementById("timer").innerText = "00:00";
}

// =======================
// WAVEFORM
// =======================

function startVisualizer(stream){

    const canvas = document.getElementById("visualizer");
    const canvasCtx = canvas.getContext("2d");

    canvas.width = canvas.offsetWidth;
    canvas.height = 90;

    audioContext = new AudioContext();
    analyser = audioContext.createAnalyser();
    source = audioContext.createMediaStreamSource(stream);

    source.connect(analyser);

    analyser.fftSize = 256;

    const bufferLength = analyser.frequencyBinCount;
    dataArray = new Uint8Array(bufferLength);

    function draw(){

        animationId = requestAnimationFrame(draw);

        analyser.getByteFrequencyData(dataArray);

        canvasCtx.fillStyle = "#0b1220";
        canvasCtx.fillRect(0,0,canvas.width,canvas.height);

        let barWidth = (canvas.width / bufferLength) * 2.5;
        let x = 0;

        for(let i=0;i<bufferLength;i++){

            let barHeight = dataArray[i] / 2;

            canvasCtx.fillStyle = "rgb(59,130,246)";
            canvasCtx.fillRect(
                x,
                canvas.height-barHeight,
                barWidth,
                barHeight
            );

            x += barWidth + 1;
        }
    }

    draw();
}

function stopVisualizer(){
    cancelAnimationFrame(animationId);
}

// =======================
// RECORDING
// =======================

async function startRecording(){

    try{

        stream = await navigator.mediaDevices.getUserMedia({audio:true});

        mediaRecorder = new MediaRecorder(stream);

        audioChunks = [];

        mediaRecorder.ondataavailable = event=>{
            if(event.data.size > 0){
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = ()=>{

            const audioBlob = new Blob(audioChunks,{type:'audio/webm'});
            const audioUrl = URL.createObjectURL(audioBlob);

            document.getElementById("audioPlayback").src = audioUrl;
        };

        mediaRecorder.start();

        document.getElementById("status").innerText="🎙 Recording...";

        startTimer();
        startVisualizer(stream);

    }catch(error){

        alert("Microphone permission denied.");
        console.log(error);
    }
}

function pauseRecording(){

    if(mediaRecorder && mediaRecorder.state==="recording"){

        mediaRecorder.pause();

        document.getElementById("status").innerText="⏸ Paused";

        stopTimer();
        stopVisualizer();
    }
}

function resumeRecording(){

    if(mediaRecorder && mediaRecorder.state==="paused"){

        mediaRecorder.resume();

        document.getElementById("status").innerText="▶ Recording Resumed";

        startTimer();
        startVisualizer(stream);
    }
}

function stopRecording(){

    if(mediaRecorder){

        mediaRecorder.stop();

        document.getElementById("status").innerText="⏹ Recording Stopped";

        stopTimer();
        stopVisualizer();
    }
}

// =======================
// UPLOAD
// =======================

async function uploadAudio(){

    stopRecording();

    setTimeout(async ()=>{

        const blob = new Blob(audioChunks,{type:'audio/webm'});

        let formData = new FormData();

        formData.append(
            "patient_name",
            document.getElementById("patient_name").value
        );

        formData.append(
            "doctor_name",
            document.getElementById("doctor_name").value
        );

        formData.append(
            "audio_file",
            blob,
            "recording.webm"
        );

        document.getElementById("status").innerText="⬆ Uploading...";

        const response = await fetch("/upload",{
            method:"POST",
            body:formData
        });

        const html = await response.text();

        document.open();
        document.write(html);
        document.close();

    },1000);
}

</script>

</body>
</html>
"""

# ==========================
# UPLOAD + WHISPER
# ==========================

@app.post("/upload", response_class=HTMLResponse)
async def upload(
    patient_name: str = Form(...),
    doctor_name: str = Form(...),
    audio_file: UploadFile = File(...)
):

    filepath = "uploads/recording.webm"

    with open(filepath, "wb") as f:
        f.write(await audio_file.read())

    with open(filepath, "rb") as f:

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )

    text = transcript.text

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
    INSERT INTO reports(
    patient_name,
    doctor_name,
    transcription,
    created_at
    )
    VALUES(?,?,?,?)
    """,(patient_name, doctor_name, text, now))

    conn.commit()

    return f"""
<html>
<body style='background:#081225;color:white;
font-family:Arial;padding:40px;'>

<h1>✅ Transcription Complete</h1>

<p><b>Patient:</b> {patient_name}</p>
<p><b>Doctor:</b> {doctor_name}</p>

<div style='background:#111827;
padding:25px;
border-radius:15px;
margin-top:20px;
font-size:18px;'>

{text}

</div>

<br><br>

<a href="/" style="color:#60a5fa;">⬅ Back</a>

</body>
</html>
"""
