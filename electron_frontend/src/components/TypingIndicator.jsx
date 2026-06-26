import React from 'react';

export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1.5">
      <span className="w-2 h-2 rounded-full bg-jarvis-accent/60 animate-typing" style={{ animationDelay: '0s' }} />
      <span className="w-2 h-2 rounded-full bg-jarvis-accent/60 animate-typing" style={{ animationDelay: '0.2s' }} />
      <span className="w-2 h-2 rounded-full bg-jarvis-accent/60 animate-typing" style={{ animationDelay: '0.4s' }} />
    </div>
  );
}
