const camera = document.querySelector("#camera");
const snapshot = document.querySelector("#snapshot");
const startButton = document.querySelector("#start-button");
const stopButton = document.querySelector("#stop-button");
const repeatButton = document.querySelector("#repeat-button");
const retakeButton = document.querySelector("#retake-button");
const captureButton = document.querySelector("#capture-button");
const usePictureButton = document.querySelector("#use-picture-button");
const sessionActions = document.querySelector("#session-actions");
const captureActions = document.querySelector("#capture-actions");
const statusText = document.querySelector("#status");
const alertStatus = document.querySelector("#alert-status");
const connectionState = document.querySelector("#connection-state");
const connectionLabel = document.querySelector("#connection-label");
const activityRegion = document.querySelector("#activity-region");
const answerPanel = document.querySelector("#answer-panel");
const answerText = document.querySelector("#answer-text");
const confidenceText = document.querySelector("#confidence-text");
const spokenStatus = document.querySelector("#spoken-status");

const STATE = Object.freeze({
    NOT_STARTED: "not_started",
    READY: "ready",
    LISTENING: "listening",
    HEARING: "hearing",
    TRANSCRIBING: "transcribing",
    QUALITY_WARNING: "quality_warning",
    ANALYZING: "analyzing",
    AWAITING_SECOND: "awaiting_second",
    SPEAKING: "speaking",
    ERROR: "error",
});

const FRAMING_MESSAGES = Object.freeze({
    move_left: "Move the camera slightly left, then take the picture again.",
    move_right: "Move the camera slightly right, then take the picture again.",
    move_closer: "Move the camera closer, then take the picture again.",
    move_farther: "Move the camera farther away, then take the picture again.",
    hold_steady: "Hold the camera steady, then take the picture again.",
    improve_lighting: "Move to better lighting, then take the picture again.",
});

const SILENCE_TO_SUBMIT_MS = 900;
const MAX_UTTERANCE_MS = 15000;
const MIN_UTTERANCE_MS = 350;
const PRE_ROLL_MS = 500;

let state = STATE.NOT_STARTED;
let mediaStream;
let audioContext;
let recorderSource;
let recorderProcessor;
let playbackSource;
let activeRequest;
let runGeneration = 0;
let sessionId;
let currentQuestion = "";
let lastAnswerAudio;
let lastAnswerText = "";
let pendingFrame;
let waitingForSecondCapture = false;
let listening = false;
let speechDetected = false;
let recordedBuffers = [];
let preRollBuffers = [];
let consecutiveVoiceBuffers = 0;
let silenceDuration = 0;
let utteranceDuration = 0;
let noiseFloor = 0.008;

spokenStatus.checked = localStorage.getItem("guardian-spoken-status") !== "false";

startButton.addEventListener("click", startAssistant);
stopButton.addEventListener("click", stopAssistant);
repeatButton.addEventListener("click", repeatAnswer);
retakeButton.addEventListener("click", () => captureAndAnalyze(currentQuestion));
captureButton.addEventListener("click", () => captureAndAnalyze(currentQuestion));
usePictureButton.addEventListener("click", submitPendingFrame);
spokenStatus.addEventListener("change", () => {
    localStorage.setItem("guardian-spoken-status", String(spokenStatus.checked));
    if (!spokenStatus.checked) {
        window.speechSynthesis?.cancel();
    }
});

function transition(nextState, message, options = {}) {
    state = nextState;
    connectionLabel.textContent = options.connection || stateLabel(nextState);
    statusText.textContent = message;
    if (options.alert) {
        statusText.dataset.tone = "alert";
    } else {
        delete statusText.dataset.tone;
    }
    document.body.dataset.running = String(nextState !== STATE.NOT_STARTED);
    document.body.dataset.state = nextState;

    const running = nextState !== STATE.NOT_STARTED;
    const busy = [STATE.TRANSCRIBING, STATE.ANALYZING, STATE.SPEAKING].includes(nextState);
    activityRegion.setAttribute("aria-busy", String(busy));
    answerPanel.setAttribute("aria-busy", String(busy));
    connectionState.dataset.tone = options.alert ? "alert" : "default";
    const captureDecision = [STATE.QUALITY_WARNING, STATE.AWAITING_SECOND].includes(nextState);
    startButton.hidden = running;
    sessionActions.hidden = !running;
    stopButton.disabled = !running;
    repeatButton.disabled = !running || !lastAnswerText || busy;
    retakeButton.disabled = !running || !currentQuestion || busy || captureDecision;

    if (options.alert) {
        alertStatus.textContent = "";
        window.setTimeout(() => {
            alertStatus.textContent = message;
        }, 20);
    }
}

function stateLabel(value) {
    const labels = {
        [STATE.NOT_STARTED]: "Not started",
        [STATE.READY]: "Ready",
        [STATE.LISTENING]: "Listening",
        [STATE.HEARING]: "Hearing you",
        [STATE.TRANSCRIBING]: "Thinking",
        [STATE.QUALITY_WARNING]: "Check picture",
        [STATE.ANALYZING]: "Thinking",
        [STATE.AWAITING_SECOND]: "Another view needed",
        [STATE.SPEAKING]: "Speaking",
        [STATE.ERROR]: "Needs attention",
    };
    return labels[value];
}

async function startAssistant() {
    const generation = ++runGeneration;
    transition(STATE.READY, "Requesting camera and microphone access.");

    try {
        audioContext = audioContext || new AudioContext();
        await audioContext.resume();
        mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: audioConstraints(),
        });
        if (generation !== runGeneration) {
            stopMediaTracks(mediaStream);
            return;
        }
        camera.srcObject = mediaStream;
        await camera.play();
        sessionId = createSessionId();

        transition(STATE.READY, "Camera and microphone ready.");
        await speakStatusMessage("Camera and microphone ready. Listening. Ask your question.");
        await startListening();
    } catch (error) {
        stopMediaTracks(mediaStream);
        mediaStream = undefined;
        transition(
            STATE.NOT_STARTED,
            "Camera and microphone access are required. Allow both permissions and try again.",
            { alert: true, connection: "Permission needed" },
        );
    }
}

function audioConstraints() {
    return {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
    };
}

async function ensureMicrophone() {
    if (mediaStream?.getAudioTracks().length) {
        return;
    }
    const microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints() });
    for (const track of microphoneStream.getAudioTracks()) {
        mediaStream.addTrack(track);
    }
}

async function startListening() {
    if (!mediaStream || listening || state === STATE.NOT_STARTED) {
        return;
    }
    await ensureMicrophone();
    resetRecorderState();
    await audioContext.resume();
    recorderSource = audioContext.createMediaStreamSource(mediaStream);
    recorderProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    recorderProcessor.onaudioprocess = handleAudioProcess;
    recorderSource.connect(recorderProcessor);
    recorderProcessor.connect(audioContext.destination);
    listening = true;
    transition(STATE.LISTENING, "Listening for a question.");
    playEarcon("listening");
}

function resetRecorderState() {
    recordedBuffers = [];
    preRollBuffers = [];
    speechDetected = false;
    consecutiveVoiceBuffers = 0;
    silenceDuration = 0;
    utteranceDuration = 0;
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
            transition(STATE.HEARING, "Listening to your question.");
        }
        return;
    }

    recordedBuffers.push(samples);
    utteranceDuration += bufferDuration;
    const voiceThreshold = Math.max(0.016, noiseFloor * 2.2);
    silenceDuration = rms > voiceThreshold ? 0 : silenceDuration + bufferDuration;
    if ((silenceDuration >= SILENCE_TO_SUBMIT_MS && utteranceDuration >= MIN_UTTERANCE_MS)
        || utteranceDuration >= MAX_UTTERANCE_MS) {
        void finishUtterance();
    }
}

async function finishUtterance() {
    if (!listening) {
        return;
    }
    const generation = runGeneration;
    listening = false;
    const wavBlob = encodeWav(recordedBuffers, audioContext.sampleRate);
    disconnectRecorder();

    try {
        transition(STATE.TRANSCRIBING, "Capturing the current view.");
        const frame = await captureFrameWithQuality();
        playEarcon("capture");
        vibrate([35]);
        void speakStatusMessage("Picture captured. Thinking.");
        transition(STATE.TRANSCRIBING, "Picture captured. Transcribing your question.");

        activeRequest = new AbortController();
        const formData = new FormData();
        formData.append("audio", wavBlob, "question.wav");
        const response = await fetch("/api/transcribe", {
            method: "POST",
            body: formData,
            signal: activeRequest.signal,
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }
        const data = await response.json();
        if (generation !== runGeneration) {
            return;
        }
        if (!data.transcript) {
            transition(STATE.ERROR, "I did not understand that. Listening again.", { alert: true });
            await speakStatusMessage("I did not understand that. Listening again.");
            await startListening();
            return;
        }
        currentQuestion = data.transcript;
        await handleCapturedFrame(frame);
    } catch (error) {
        await handleFlowError(error, generation, "I could not process that question.");
    } finally {
        activeRequest = undefined;
    }
}

async function captureAndAnalyze(question) {
    if (!mediaStream || !question || state === STATE.ANALYZING) {
        return;
    }
    const generation = runGeneration;
    disconnectRecorder();
    pendingFrame = undefined;
    captureActions.hidden = true;
    try {
        transition(STATE.TRANSCRIBING, "Capturing the current view.");
        const frame = await captureFrameWithQuality();
        playEarcon("capture");
        vibrate([35]);
        await speakStatusMessage("Picture captured. Thinking.");
        if (generation !== runGeneration) {
            return;
        }
        await handleCapturedFrame(frame);
    } catch (error) {
        await handleFlowError(error, generation, "The picture could not be captured.");
    }
}

async function handleCapturedFrame(frame) {
    if (frame.guidance) {
        pendingFrame = frame.blob;
        transition(STATE.QUALITY_WARNING, frame.guidance, { alert: true });
        captureActions.hidden = false;
        setCaptureButtonLabel("Take picture again");
        usePictureButton.hidden = false;
        playEarcon("warning");
        vibrate([80, 50, 80]);
        await speakStatusMessage(`${frame.guidance} Take the picture again, or use this picture.`);
        captureButton.focus();
        return;
    }
    await submitFrame(frame.blob);
}

async function submitPendingFrame() {
    if (!pendingFrame) {
        return;
    }
    const frame = pendingFrame;
    pendingFrame = undefined;
    captureActions.hidden = true;
    await submitFrame(frame);
}

async function submitFrame(frameBlob) {
    const generation = runGeneration;
    transition(STATE.ANALYZING, "Analyzing the picture.");
    playEarcon("processing");
    activeRequest = new AbortController();
    const formData = new FormData();
    formData.append("question", currentQuestion);
    formData.append("frame", frameBlob, "camera-frame.jpg");
    formData.append("session_id", sessionId);

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            body: formData,
            signal: activeRequest.signal,
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }
        const data = await response.json();
        if (generation !== runGeneration) {
            return;
        }
        sessionId = data.session_id;
        waitingForSecondCapture = data.needs_second_capture;
        await renderResult(data, generation);
    } catch (error) {
        await handleFlowError(error, generation, "Analysis failed.");
    } finally {
        activeRequest = undefined;
    }
}

async function renderResult(data, generation) {
    lastAnswerText = data.text;
    lastAnswerAudio = data.audio_base64;
    answerText.textContent = data.text;
    confidenceText.textContent = `${data.confidence_band} confidence`;
    answerPanel.hidden = false;
    repeatButton.disabled = false;
    retakeButton.disabled = false;

    if (data.audio_base64) {
        transition(STATE.SPEAKING, "Playing the spoken answer.");
        try {
            await playBase64Audio(data.audio_base64);
        } catch (error) {
            if (error.name !== "AbortError") {
                await speakStatusMessage(data.text, true);
            }
        }
    } else {
        transition(STATE.SPEAKING, "Speaking the answer.");
        await speakStatusMessage(data.text, true);
    }
    if (generation !== runGeneration) {
        return;
    }

    if (data.needs_second_capture) {
        transition(STATE.AWAITING_SECOND, "Another view is needed for a more reliable answer.");
        captureActions.hidden = false;
        setCaptureButtonLabel("Take another picture");
        usePictureButton.hidden = true;
        await speakStatusMessage("Another view is needed. Point the camera at the item, then take another picture.");
        captureButton.focus();
        return;
    }

    const framingMessage = FRAMING_MESSAGES[data.framing_action];
    if (framingMessage) {
        transition(STATE.READY, framingMessage);
        captureActions.hidden = false;
        setCaptureButtonLabel("Take picture again");
        usePictureButton.hidden = true;
        await speakStatusMessage(framingMessage);
        return;
    }

    transition(STATE.READY, "Answer complete. Listening for another question.");
    await speakStatusMessage("Listening for another question.");
    await startListening();
}

function setCaptureButtonLabel(label) {
    const labelElement = captureButton.querySelector("span");
    if (labelElement) {
        labelElement.textContent = label;
    } else {
        captureButton.textContent = label;
    }
}

async function repeatAnswer() {
    if (!lastAnswerText || state === STATE.ANALYZING) {
        return;
    }
    disconnectRecorder();
    stopPlayback();
    transition(STATE.SPEAKING, "Repeating the answer.");
    try {
        if (lastAnswerAudio) {
            await playBase64Audio(lastAnswerAudio);
        } else {
            await speakStatusMessage(lastAnswerText, true);
        }
    } catch (error) {
        if (error.name !== "AbortError") {
            transition(STATE.ERROR, "The answer could not be replayed.", { alert: true });
        }
    }
    if (state !== STATE.NOT_STARTED) {
        transition(STATE.READY, "Listening for another question.");
        await startListening();
    }
}

async function stopAssistant() {
    const oldSessionId = sessionId;
    runGeneration += 1;
    activeRequest?.abort();
    activeRequest = undefined;
    window.speechSynthesis?.cancel();
    stopPlayback();
    disconnectRecorder();
    stopMediaTracks(mediaStream);
    mediaStream = undefined;
    camera.srcObject = null;
    sessionId = undefined;
    currentQuestion = "";
    lastAnswerAudio = undefined;
    lastAnswerText = "";
    waitingForSecondCapture = false;
    pendingFrame = undefined;
    captureActions.hidden = true;
    answerPanel.hidden = true;
    transition(STATE.NOT_STARTED, "Assistant stopped. Start again when ready.");
    startButton.focus();

    if (oldSessionId) {
        try {
            await fetch(`/api/sessions/${encodeURIComponent(oldSessionId)}`, { method: "DELETE" });
        } catch (error) {
            // The local interaction is already stopped; server cleanup is best effort.
        }
    }
}

async function handleFlowError(error, generation, message) {
    if (error.name === "AbortError" || generation !== runGeneration) {
        return;
    }
    transition(STATE.ERROR, `${message} Listening again.`, { alert: true });
    playEarcon("error");
    vibrate([120, 60, 120]);
    await speakStatusMessage(message);
    await startListening();
}

async function captureFrameWithQuality() {
    const width = camera.videoWidth;
    const height = camera.videoHeight;
    if (!width || !height) {
        throw new Error("Camera is not ready.");
    }
    snapshot.width = width;
    snapshot.height = height;
    const context = snapshot.getContext("2d", { willReadFrequently: true });
    context.drawImage(camera, 0, 0, width, height);
    const blob = await new Promise((resolve, reject) => {
        snapshot.toBlob((result) => result ? resolve(result) : reject(new Error("Capture failed.")), "image/jpeg", 0.88);
    });
    return { blob, guidance: assessImageQuality(snapshot) };
}

function assessImageQuality(sourceCanvas) {
    const sample = document.createElement("canvas");
    sample.width = 160;
    sample.height = 120;
    const context = sample.getContext("2d", { willReadFrequently: true });
    context.drawImage(sourceCanvas, 0, 0, sample.width, sample.height);
    const pixels = context.getImageData(0, 0, sample.width, sample.height).data;
    const luminance = new Float32Array(sample.width * sample.height);
    let luminanceTotal = 0;
    for (let pixel = 0, index = 0; pixel < pixels.length; pixel += 4, index += 1) {
        const value = (0.2126 * pixels[pixel]) + (0.7152 * pixels[pixel + 1]) + (0.0722 * pixels[pixel + 2]);
        luminance[index] = value;
        luminanceTotal += value;
    }
    const meanLuminance = luminanceTotal / luminance.length;
    if (meanLuminance < 32) {
        return "The picture may be too dark. Move to better lighting.";
    }

    let laplacianTotal = 0;
    let laplacianSquaredTotal = 0;
    let count = 0;
    for (let y = 1; y < sample.height - 1; y += 1) {
        for (let x = 1; x < sample.width - 1; x += 1) {
            const index = (y * sample.width) + x;
            const value = (4 * luminance[index])
                - luminance[index - 1]
                - luminance[index + 1]
                - luminance[index - sample.width]
                - luminance[index + sample.width];
            laplacianTotal += value;
            laplacianSquaredTotal += value * value;
            count += 1;
        }
    }
    const variance = (laplacianSquaredTotal / count) - ((laplacianTotal / count) ** 2);
    return variance < 18 ? "The picture may be blurry. Hold the camera steady." : null;
}

async function speakStatusMessage(message, force = false) {
    if ((!spokenStatus.checked && !force) || !window.speechSynthesis || state === STATE.NOT_STARTED) {
        return;
    }
    disconnectRecorder();
    window.speechSynthesis.cancel();
    await new Promise((resolve) => {
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.onend = resolve;
        utterance.onerror = resolve;
        window.speechSynthesis.speak(utterance);
    });
}

function playEarcon(type) {
    if (!audioContext || audioContext.state === "closed") {
        return;
    }
    const tones = {
        listening: [740, 0.09],
        capture: [1040, 0.07],
        processing: [440, 0.12],
        warning: [330, 0.2],
        error: [220, 0.28],
    };
    const spec = tones[type];
    if (!spec) {
        return;
    }
    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.frequency.value = spec[0];
    gain.gain.setValueAtTime(0.12, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + spec[1]);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + spec[1]);
}

function vibrate(pattern) {
    if (navigator.vibrate) {
        navigator.vibrate(pattern);
    }
}

async function playBase64Audio(encodedAudio) {
    await audioContext.resume();
    const binaryAudio = window.atob(encodedAudio);
    const audioBytes = Uint8Array.from(binaryAudio, (character) => character.charCodeAt(0));
    const audioBuffer = await audioContext.decodeAudioData(audioBytes.buffer);
    await new Promise((resolve, reject) => {
        playbackSource = audioContext.createBufferSource();
        playbackSource.buffer = audioBuffer;
        playbackSource.connect(audioContext.destination);
        playbackSource.addEventListener("ended", resolve, { once: true });
        try {
            playbackSource.start();
        } catch (error) {
            reject(error);
        }
    });
    playbackSource?.disconnect();
    playbackSource = undefined;
}

function stopPlayback() {
    if (!playbackSource) {
        return;
    }
    try {
        playbackSource.stop();
    } catch (error) {
        // The source may already have ended.
    }
    playbackSource.disconnect();
    playbackSource = undefined;
}

function disconnectRecorder() {
    listening = false;
    if (recorderProcessor) {
        recorderProcessor.disconnect();
        recorderProcessor.onaudioprocess = null;
    }
    recorderSource?.disconnect();
    recorderProcessor = undefined;
    recorderSource = undefined;
}

function stopMediaTracks(stream) {
    for (const track of stream?.getTracks() || []) {
        track.stop();
    }
}

function createSessionId() {
    return window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
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
