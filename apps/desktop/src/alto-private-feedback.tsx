import { useState } from "react";
import { altoRequest, type AltoApiContext, type EmployeePreference } from "./alto-api";
import { PreferenceConsentCard } from "./alto-pages";
import { Badge, ErrorNotice, Icon, Modal } from "./alto-ui";
import { humanize, useCommand, useResource } from "./alto-state";
export function PrivateFeedback({ api, taskId }: {
    api: AltoApiContext;
    taskId?: string;
}) {
    const resource = useResource<{
        preferences: EmployeePreference[];
    }>(api, "/me/employee-preferences");
    const command = useCommand();
    const [dialog, setDialog] = useState<"feedback" | "preference" | null>(null);
    const [text, setText] = useState("");
    const [suggest, setSuggest] = useState(false);
    const [selected, setSelected] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const preference = resource.data?.preferences.find((item) => item.id === selected);
    return <section className="alto-private-feedback">
<header>
<Icon name="lock" size={19}/>
<h2>Your private feedback & preferences</h2>
</header>
<p>Feedback stays private. A suggestion is never shared unless you approve its exact text and named audience.</p>
<div className="alto-button-row">
<button className="alto-secondary" onClick={() => { setDialog("feedback"); setText(""); setSaved(false); }}>Record private feedback</button>
<button className="alto-secondary" onClick={() => { setDialog("preference"); setText(""); setSaved(false); }}>Write a preference</button>
</div>{saved && <p className="alto-caption" role="status">Saved privately. Nothing was shared.</p>}{resource.data?.preferences.map((item) => <button className="alto-preference-row" key={item.id} onClick={() => setSelected(item.id)}>
<span>{item.text}</span>
<Badge tone={item.status === "shared" ? "mint" : "neutral"}>{humanize(item.status)}</Badge>
</button>)}<ErrorNotice error={resource.error} retry={resource.refresh}/>
    {dialog && <Modal title={dialog === "feedback" ? "Private work feedback" : "Write your own preference"} onClose={() => setDialog(null)}>
<p>This is private to your current employee identity. Avoid including another person’s private information.</p>
<label className="alto-field">{dialog === "feedback" ? "What worked well, or what would help next time?" : "What would you like future planning to take into account?"}<textarea rows={5} value={text} maxLength={dialog === "feedback" ? 10000 : 1000} onChange={(event) => setText(event.target.value)}/>
</label>{dialog === "feedback" && <label className="alto-checkbox">
<input type="checkbox" checked={suggest} onChange={(event) => setSuggest(event.target.checked)}/>Ask ALTO to suggest a private preference for me to review.</label>}<button className="alto-primary" disabled={command.busy || !text.trim()} onClick={() => void command.run(async () => { await altoRequest(api, dialog === "feedback" ? "/me/feedback" : "/me/employee-preferences", { method: "POST", body: dialog === "feedback" ? { text: text.trim(), task_id: taskId ?? null, suggest_preference: suggest } : { text: text.trim() } }); setDialog(null); setText(""); setSaved(true); resource.refresh(); })}>Save privately</button>
<ErrorNotice error={command.error}/>
</Modal>}
    {preference && <Modal title="Your preference and audience" onClose={() => setSelected(null)}>
<PreferenceConsentCard api={api} preference={preference} onClose={() => setSelected(null)} onSaved={resource.refresh}/>
</Modal>}
  </section>;
}
