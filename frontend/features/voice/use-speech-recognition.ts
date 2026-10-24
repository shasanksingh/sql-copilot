"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type RecognitionResultLike = { isFinal: boolean; [index: number]: { transcript: string } };
type RecognitionEventLike = Event & { resultIndex: number; results: { length: number; [index: number]: RecognitionResultLike } };
type RecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionConstructor = new () => RecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

type VoiceOptions = {
  onTranscript: (value: string) => void;
  onFinal?: (value: string) => void;
};

export function useSpeechRecognition({ onTranscript, onFinal }: VoiceOptions) {
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const seedRef = useRef("");
  const keepListeningRef = useRef(false);
  const transcriptRef = useRef(onTranscript);
  const finalRef = useRef(onFinal);
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);

  useEffect(() => {
    transcriptRef.current = onTranscript;
    finalRef.current = onFinal;
  }, [onFinal, onTranscript]);

  useEffect(() => {
    setIsSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
    return () => {
      keepListeningRef.current = false;
      recognitionRef.current?.stop();
    };
  }, []);

  const start = useCallback((existingText: string) => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return false;
    keepListeningRef.current = true;
    recognitionRef.current?.stop();
    seedRef.current = existingText.trim();
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      let finalTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const value = event.results[index][0]?.transcript ?? "";
        transcript += value;
        if (event.results[index].isFinal) finalTranscript += value;
      }
      const combined = [seedRef.current, transcript.trim()].filter(Boolean).join(seedRef.current && transcript ? " " : "");
      transcriptRef.current(combined);
      if (finalTranscript.trim()) {
        finalRef.current?.(combined.trim());
        // Continue listening for the next request. The final utterance has
        // already been submitted, so it must not seed the next request.
        seedRef.current = "";
      }
    };
    recognition.onerror = (event) => {
      if (event.error !== "no-speech" && event.error !== "aborted") setIsListening(false);
    };
    recognition.onend = () => {
      if (!keepListeningRef.current) {
        setIsListening(false);
        return;
      }
      // Chromium ends recognition after short pauses. Restart only while the
      // user has explicitly left Voice on; the second click always stops it.
      window.setTimeout(() => {
        if (!keepListeningRef.current) return;
        try {
          recognition.start();
          setIsListening(true);
        } catch {
          setIsListening(false);
        }
      }, 160);
    };
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    return true;
  }, []);

  const stop = useCallback(() => {
    keepListeningRef.current = false;
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);
  return { isSupported, isListening, start, stop };
}
