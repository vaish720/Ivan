// Voice input and output for the chat page.
//
// Phase 1 Step 1 uses the browser's own speech services. Step 2 will swap in our own
// streaming pipeline behind the same interface, so chat.html doesn't change:
//   Voice.supported / Voice.canSpeak
//   Voice.listen({ onInterim, onFinal, onError, onEnd })   Voice.stopListening()
//   Voice.speak(text, onEnd)                               Voice.stopSpeaking()
//
// Note: Chrome sends the audio to Google and Edge to Microsoft for recognition.
// That's fine for the sample calendar; decide again before real client data.

const Voice = (() => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  let recognizer = null;
  let voice = null;

  function pickVoice() {
    const english = (synth ? synth.getVoices() : []).filter(v => (v.lang || "").toLowerCase().startsWith("en"));
    voice = english.find(v => /natural/i.test(v.name))          // Edge's neural voices sound far better
         || english.find(v => v.lang === navigator.language)
         || english[0] || null;
  }
  if (synth) { pickVoice(); synth.onvoiceschanged = pickVoice; }

  // Times read better as "15:00 to 15:30" than "15:00 dash 15:30".
  function forSpeech(text) {
    return text.replace(/(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})/g, "$1 to $2").replace(/[*_#`]/g, "");
  }

  function listen({ onInterim, onFinal, onError, onEnd } = {}) {
    stopSpeaking();
    if (recognizer) recognizer.abort();
    const r = new Recognition();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;  // stop when the Rep stops talking
    let finalText = "";
    r.onresult = e => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t; else interim += t;
      }
      onInterim && onInterim((finalText + interim).trim());
    };
    r.onerror = e => { if (e.error !== "aborted") onError && onError(e.error); };
    r.onend = () => {
      recognizer = null;
      onEnd && onEnd();
      if (finalText.trim()) onFinal && onFinal(finalText.trim());
    };
    recognizer = r;
    r.start();
  }

  function stopListening() { if (recognizer) recognizer.stop(); }

  function speak(text, onEnd) {
    if (!synth) { onEnd && onEnd(); return; }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(forSpeech(text));
    if (voice) u.voice = voice;
    u.onend = () => onEnd && onEnd();
    u.onerror = () => onEnd && onEnd();
    synth.speak(u);
  }

  function stopSpeaking() { if (synth) synth.cancel(); }

  return {
    supported: !!Recognition,
    canSpeak: !!synth,
    listen, stopListening, speak, stopSpeaking,
    get listening() { return recognizer !== null; },
  };
})();
