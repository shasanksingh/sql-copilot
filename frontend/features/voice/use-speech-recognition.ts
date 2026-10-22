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

export function useSpeechRecognition(onTranscript: (value: string) => void) {
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const seedRef = useRef("");
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);

  useEffect(() => {
    setIsSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
    return () => recognitionRef.current?.stop();
  }, []);

  const start = useCallback((existingText: string) => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return false;
    recognitionRef.current?.stop();
    seedRef.current = existingText.trim();
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript ?? "";
      }
      onTranscript([seedRef.current, transcript.trim()].filter(Boolean).join(seedRef.current && transcript ? " " : ""));
    };
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    return true;
  }, [onTranscript]);

  const stop = useCallback(() => recognitionRef.current?.stop(), []);
  return { isSupported, isListening, start, stop };
}
