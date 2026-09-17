const camera = document.querySelector("#camera");
const snapshot = document.querySelector("#snapshot");
const startButton = document.querySelector("#start-button");
const statusText = document.querySelector("#status");
const connectionState = document.querySelector("#connection-state");
const questionText = document.querySelector("#question-text");
const answerPanel = document.querySelector("#answer-panel");
const answerText = document.querySelector("#answer-text");
const confidenceText = document.querySelector("#confidence-text");

let mediaStream;
let sessionId;
let waitingForSecondCapture = false;
let audioContext;
let audioSource;
let audioProcessor;
let recordedBuffers = [];
let preRollBuffers = [];
let listening = false;
let speechDetected = false;
let consecutiveVoiceBuffers = 0;
let silenceDuration = 0;
let utteranceDuration = 0;
let noiseFloor = 0.008;
let currentQuestion = "";
let questionFramePromise;

const SILENCE_TO_SUBMIT_MS = 900;
const MAX_UTTERANCE_MS = 15000;
const MIN_UTTERANCE_MS = 350;
const PRE_ROLL_MS = 500;

startButton.addEventListener("click", startMedia);

async function startMedia() {
    setStatus("Requesting camera and microphone access.");
    try {
        audioContext = new AudioContext();
        await audioContext.resume();
        mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                channelCount: 1,
            },
        });
        camera.srcObject = mediaStream;
        await camera.play();

        startButton.disabled = true;
        startButton.querySelector("span:last-child").textContent = "Assistant running";
        document.body.dataset.running = "true";
        connectionState.textContent = "Listening";
        await startListening();
    } catch (error) {
        connectionState.textContent = "Permission needed";
        setStatus(
            "Camera and microphone access are required. Use HTTPS or localhost, then allow both permissions.",
            "alert",
        );
    }
}

async function startListening() {
    if (!mediaStream || listening || waitingForSecondCapture) {
        return;
    }

    recordedBuffers = [];
    preRollBuffers = [];
    speechDetected = false;
    consecutiveVoiceBuffers = 0;
    silenceDuration = 0;
    utteranceDuration = 0;
    if (!audioContext || audioContext.state === "closed") {
        audioContext = new AudioContext();
    }
    await audioContext.resume();
    audioSource = audioContext.createMediaStreamSource(mediaStream);
    audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    audioProcessor.onaudioprocess = handleAudioProcess;
    audioSource.connect(audioProcessor);
    audioProcessor.connect(audioContext.destination);
    listening = true;
    connectionState.textContent = "Listening";
    setStatus("Listening for a question.");
}

function handleAudioProcess(event) {
    if (!listening) {
        return;
    }

    const samples = new Float32Array(event.inputBuffer.getChannelData(0));
    const bufferDuration = (samples.length / audioContext.sampleRate) * 1000;
    let sumOfSquares = 0;
    for (const sample of samples) {
        sumOfSquares += sample * sample;
    }
    const rms = Math.sqrt(sumOfSquares / samples.length);

    if (!speechDetected) {
        noiseFloor = (noiseFloor * 0.95) + (Math.min(rms, 0.04) * 0.05);
        const maxPreRollBuffers = Math.ceil(PRE_ROLL_MS / bufferDuration);
        preRollBuffers.push(samples);
        if (preRollBuffers.length > maxPreRollBuffers) {
            preRollBuffers.shift();
        }

        const voiceThreshold = Math.max(0.018, noiseFloor * 2.8);
        consecutiveVoiceBuffers = rms > voiceThreshold ? consecutiveVoiceBuffers + 1 : 0;
        if (consecutiveVoiceBuffers >= 2) {
            speechDetected = true;
            recordedBuffers = [...preRollBuffers];
            utteranceDuration = preRollBuffers.length * bufferDuration;
            questionFramePromise = captureFrame();
            connectionState.textContent = "Hearing you";
            setStatus("Listening to your question.");
        }
        return;
    }

    recordedBuffers.push(samples);
    utteranceDuration += bufferDuration;
    const voiceThreshold = Math.max(0.016, noiseFloor * 2.2);
    silenceDuration = rms > voiceThreshold ? 0 : silenceDuration + bufferDuration;

    if (
        (silenceDuration >= SILENCE_TO_SUBMIT_MS && utteranceDuration >= MIN_UTTERANCE_MS)
        || utteranceDuration >= MAX_UTTERANCE_MS
    ) {
        void finishUtterance();
    }
}

async function finishUtterance() {
    if (!listening) {
        return;
    }

    listening = false;
    const sampleRate = audioContext.sampleRate;
    disconnectRecorder();

    const wavBlob = encodeWav(recordedBuffers, sampleRate);

    setStatus("Transcribing your question.");
    connectionState.textContent = "Thinking";
    const formData = new FormData();
    formData.append("audio", wavBlob, "question.wav");

    try {
        const response = await fetch("/api/transcribe", {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }
        const data = await response.json();
        if (!data.transcript) {
            setStatus("I did not understand that. Listening again.");
            await startListening();
            return;
        }
        currentQuestion = data.transcript;
        questionText.classList.remove("placeholder");
        questionText.textContent = currentQuestion;
        setStatus("Analyzing the current view.");
        await submitCurrentView();
    } catch (error) {
        setStatus("I could not process that question. Listening again.", "alert");
        await startListening();
    }
}

async function submitCurrentView() {
    if (!mediaStream) {
        setStatus("Press Start before analyzing the view.", "alert");
        return;
    }

    if (!currentQuestion) {
        await startListening();
        return;
    }

    setStatus(waitingForSecondCapture ? "Capturing a second view." : "Capturing and analyzing the current view.");

    try {
        const frameBlob = waitingForSecondCapture
            ? await captureFrame()
            : await questionFramePromise;
        questionFramePromise = undefined;
        const formData = new FormData();
        formData.append("question", currentQuestion);
        formData.append("frame", frameBlob, "camera-frame.jpg");
        if (sessionId) {
            formData.append("session_id", sessionId);
        }

        const response = await fetch("/api/analyze", {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }
        const data = await response.json();
        sessionId = data.session_id;
        waitingForSecondCapture = data.needs_second_capture;
        await renderResultAudioFirst(data);
    } catch (error) {
        waitingForSecondCapture = false;
        setStatus("Analysis failed. Listening for another question.", "alert");
    } finally {
        if (waitingForSecondCapture) {
            setStatus("Capturing another view for a more reliable answer.");
            window.setTimeout(() => void submitCurrentView(), 1400);
        } else {
            currentQuestion = "";
            await startListening();
        }
    }
}

async function renderResultAudioFirst(data) {
    answerText.textContent = data.text;
    confidenceText.textContent = `${data.confidence_band} confidence`;
    answerPanel.hidden = false;

    if (data.audio_base64) {
        connectionState.textContent = "Speaking";
        setStatus("Playing the spoken answer.");
        try {
            await playBase64Audio(data.audio_base64);
        } catch (error) {
            setStatus("The spoken answer could not be played.", "alert");
        }
    } else {
        setStatus("No spoken answer was generated.", "alert");
    }

    if (data.needs_second_capture) {
        setStatus("A second view is needed. Keep the camera pointed at the scene.");
    } else {
        setStatus("Answer complete. Listening for another question.");
    }
}

async function playBase64Audio(encodedAudio) {
    if (audioContext.state === "suspended") {
        await audioContext.resume();
    }

    const binaryAudio = window.atob(encodedAudio);
    const audioBytes = new Uint8Array(binaryAudio.length);
    for (let index = 0; index < binaryAudio.length; index += 1) {
        audioBytes[index] = binaryAudio.charCodeAt(index);
    }

    const audioBuffer = await audioContext.decodeAudioData(audioBytes.buffer);
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    await new Promise((resolve) => {
        source.addEventListener("ended", resolve, { once: true });
        source.start();
    });
    source.disconnect();
}

function captureFrame() {
    return new Promise((resolve, reject) => {
        const width = camera.videoWidth;
        const height = camera.videoHeight;
        if (!width || !height) {
            reject(new Error("Camera is not ready."));
            return;
        }
        snapshot.width = width;
        snapshot.height = height;
        const context = snapshot.getContext("2d");
        context.drawImage(camera, 0, 0, width, height);
        snapshot.toBlob((blob) => {
            if (blob) {
                resolve(blob);
            } else {
                reject(new Error("Could not capture a frame."));
            }
        }, "image/jpeg", 0.88);
    });
}

function encodeWav(buffers, sampleRate) {
    const samples = flattenBuffers(buffers);
    const dataLength = samples.length * 2;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, "data");
    view.setUint32(40, dataLength, true);

    let offset = 44;
    for (const sample of samples) {
        const clipped = Math.max(-1, Math.min(1, sample));
        view.setInt16(offset, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true);
        offset += 2;
    }

    return new Blob([view], { type: "audio/wav" });
}

function flattenBuffers(buffers) {
    const length = buffers.reduce((total, buffer) => total + buffer.length, 0);
    const result = new Float32Array(length);
    let offset = 0;
    for (const buffer of buffers) {
        result.set(buffer, offset);
        offset += buffer.length;
    }
    return result;
}

function writeString(view, offset, value) {
    for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
    }
}

function disconnectRecorder() {
    if (audioProcessor) {
        audioProcessor.disconnect();
        audioProcessor.onaudioprocess = null;
    }
    if (audioSource) {
        audioSource.disconnect();
    }
    audioProcessor = undefined;
    audioSource = undefined;
}

function setStatus(message, tone = "default") {
    statusText.textContent = message;
    if (tone === "alert") {
        statusText.dataset.tone = "alert";
    } else {
        delete statusText.dataset.tone;
    }
}