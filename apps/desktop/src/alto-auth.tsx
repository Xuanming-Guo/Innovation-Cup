import { useState, type RefObject } from "react";
import type { AuthorisedSessionController, AuthorisedSessionState } from "./authorised-session";
import type { PublicRuntimeConfig } from "./runtime-config";
import { AltoLogo, ErrorNotice } from "./alto-ui";
import { navigate } from "./alto-state";
export function AuthView({ config, session, controller }: {
    config: PublicRuntimeConfig;
    session: AuthorisedSessionState;
    controller: RefObject<AuthorisedSessionController | null>;
}) {
    const [mode, setMode] = useState<"signin" | "signup">("signin");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [name, setName] = useState("");
    const [role, setRole] = useState<"manager" | "employee">("manager");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    async function submit() {
        if (!controller.current || busy)
            return;
        setBusy(true);
        setError(null);
        setNotice(null);
        try {
            if (session.status === "company_required")
                await controller.current.onboard(name, role);
            else if (mode === "signup") {
                const value = await controller.current.signUp(email.trim(), password);
                if (value.confirmationRequired)
                    setNotice("Check your email to confirm your account, then sign in here.");
            }
            else
                await controller.current.signIn(email.trim(), password);
            setPassword("");
        }
        catch (value) {
            setError(value instanceof Error ? value.message : "Authentication failed.");
        }
        finally {
            setBusy(false);
        }
    }
    if (!config.supabaseConfigured)
        return <div className="alto-welcome">
<AltoLogo />
<h1>A little less coordinating.<br />A little more moving forward.</h1>
<p>Connect this installation to your organisation’s authenticated workspace to get started.</p>
<button className="alto-primary" onClick={() => navigate("/settings/deployment")}>Set up this installation</button>
<p className="alto-caption">Only public connection settings are saved on this device. Provider and database credentials stay on the server.</p>
</div>;
    const onboarding = session.status === "company_required";
    return <div className="alto-auth">
<AltoLogo />
<h1>{onboarding ? "Your ALTO demo workspace" : mode === "signin" ? "Welcome to ALTO" : "Create your account"}</h1>
<p>{onboarding ? "Choose your role in the fixed synthetic company. This does not grant production administration." : "Sign in securely to your company workspace."}</p>
<form onSubmit={(event) => { event.preventDefault(); void submit(); }}>{onboarding ? <>
<label className="alto-field">Your name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} autoComplete="name"/>
</label>
<label className="alto-field">Demo role<select value={role} onChange={(event) => setRole(event.target.value as "manager" | "employee")}>
<option value="manager">Manager — coordinate a demo run</option>
<option value="employee">Employee — start with your own empty workspace</option>
</select>
</label>
</> : <>
<label className="alto-field">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username"/>
</label>
<label className="alto-field">Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === "signup" ? 8 : undefined} autoComplete={mode === "signup" ? "new-password" : "current-password"}/>
</label>
</>}<button className="alto-primary" disabled={busy || (onboarding ? !name.trim() : !email.trim() || !password)}>{busy ? "Please wait…" : onboarding ? "Join the synthetic demo" : mode === "signin" ? "Sign in" : "Create account"}</button>
</form>
<ErrorNotice error={error}/>{notice && <div className="alto-info-banner" role="status">{notice}</div>}{!onboarding && <button className="alto-text-button" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); }}>{mode === "signin" ? "New here? Create an account" : "Already have an account? Sign in"}</button>}<button className="alto-text-button" onClick={() => navigate("/settings/deployment")}>Connection settings</button>
</div>;
}
