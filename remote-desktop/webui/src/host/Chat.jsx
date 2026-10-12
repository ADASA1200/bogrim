import { useState } from "react";
import { Button, Input } from "../components/ui";

export function Chat({ messages, onSend }) {
  const [text, setText] = useState("");
  function submit(e) {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText("");
  }
  return (
    <div className="mt-2" style={{ display: "flex", flexDirection: "column" }}>
      <div className="chat-log" style={{ maxHeight: 160 }}>
        {messages.length === 0 && <p className="text-faint">אין הודעות עדיין</p>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.from === "me" ? "me" : "them"}`}>
            {m.text}
          </div>
        ))}
      </div>
      <form className="chat-input-row" onSubmit={submit}>
        <Input placeholder="הקלידו הודעה..." value={text} onChange={(e) => setText(e.target.value)} />
        <Button variant="primary" type="submit">שלח</Button>
      </form>
    </div>
  );
}
