import { useState } from "react";
import { altoRequest, type AltoApiContext, type CalendarData, type CalendarItem, type Person } from "./alto-api";
import { Assistant } from "./alto-assistant";
import { PrivateFeedback } from "./alto-private-feedback";
import { Badge, EmptyState, ErrorNotice, Icon, IconButton, Loading, Modal, PageHeading } from "./alto-ui";
import { dateTime, formatDate, humanize, initials, navigate, useCommand, useResource } from "./alto-state";
function dayKey(value: string, timezone: string): string { const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: timezone }).formatToParts(new Date(value)); return `${parts.find((part) => part.type === "year")?.value}-${parts.find((part) => part.type === "month")?.value}-${parts.find((part) => part.type === "day")?.value}`; }
function minutesOfDay(value: string, timezone: string): number { const parts = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: timezone }).formatToParts(new Date(value)); return Number(parts.find((part) => part.type === "hour")?.value ?? 0) * 60 + Number(parts.find((part) => part.type === "minute")?.value ?? 0); }
function addDays(value: string, days: number): string { const date = new Date(`${value}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10); }
function mondayOf(value: string): string { const date = new Date(value); const day = date.getUTCDay(); return addDays(date.toISOString().slice(0, 10), day === 0 ? -6 : 1 - day); }
/** Events have distinct types and IDs; no drag/drop can silently change commitments. */
function CalendarGrid({ items, timezone, week, selectedId, selectedDay, onSelect, onDay, compact = false }: {
    items: CalendarItem[];
    timezone: string;
    week: string;
    selectedId?: string | null;
    selectedDay?: string;
    onSelect?: (item: CalendarItem) => void;
    onDay?: (day: string) => void;
    compact?: boolean;
}) {
    const days = Array.from({ length: 5 }, (_, index) => addDays(week, index));
    const startHour = 8, endHour = 18;
    return <div className={`alto-calendar-grid ${compact ? "compact" : ""}`}>
    <div className="alto-calendar-corner"/>{days.map((day) => <button key={day} className={`alto-calendar-day-heading ${day === selectedDay ? "selected" : ""}`} onClick={() => onDay?.(day)} disabled={!onDay}>{formatDate(`${day}T12:00:00Z`, { weekday: "short", month: "short", day: "numeric" }, "UTC")}</button>)}
    <div className="alto-calendar-hours">{Array.from({ length: endHour - startHour + 1 }, (_, index) => <span key={index} style={{ top: `${index / (endHour - startHour) * 100}%` }}>{String(index + startHour).padStart(2, "0")}:00</span>)}</div>
    {days.map((day) => {
            const dayItems = items.filter((item) => dayKey(item.start_at, timezone) <= day && dayKey(item.end_at, timezone) >= day && (dayKey(item.start_at, timezone) === day || item.kind !== "deadline")).map((item) => ({ item, start: Math.max(startHour * 60, dayKey(item.start_at, timezone) < day ? 0 : minutesOfDay(item.start_at, timezone)), end: Math.min(endHour * 60, dayKey(item.end_at, timezone) > day ? 1440 : minutesOfDay(item.end_at, timezone)) })).filter(({ item, start, end }) => start < endHour * 60 && (end > startHour * 60 || item.kind === "deadline")).sort((a, b) => a.start - b.start || b.end - a.end);
            const laneEnds: number[] = [];
            const positioned = dayItems.map((entry) => { let lane = laneEnds.findIndex((end) => end <= entry.start); if (lane < 0)
                lane = laneEnds.length; laneEnds[lane] = Math.max(entry.end, entry.start + 15); return { ...entry, lane }; });
            return <div className={`alto-calendar-day ${day === selectedDay ? "selected" : ""}`} key={day}>{positioned.map(({ item, start, end, lane }) => {
                    const concurrent = positioned.filter((other) => other.start < Math.max(end, start + 15) && Math.max(other.end, other.start + 15) > start);
                    const lanes = Math.max(...concurrent.map((other) => other.lane), lane) + 1;
                    return <button key={item.id} className={`alto-calendar-event ${item.kind} ${selectedId === item.id ? "selected" : ""}`} title={`${item.title}: ${dateTime(item.start_at, timezone)} – ${dateTime(item.end_at, timezone)} (${timezone})`} disabled={!onSelect} style={{ top: `${(start - startHour * 60) / ((endHour - startHour) * 60) * 100}%`, height: item.kind === "deadline" ? "25px" : `${Math.max(end - start, 25) / ((endHour - startHour) * 60) * 100}%`, left: `calc(${lane / lanes * 100}% + 3px)`, width: `calc(${100 / lanes}% - 6px)` }} onClick={() => onSelect?.(item)}>{item.kind === "deadline" && <Icon name="flag" size={14}/>}<strong>{compact ? "Busy" : item.title}</strong>{!compact && item.kind !== "deadline" && <>
<span>{formatDate(item.start_at, { hour: "2-digit", minute: "2-digit" }, timezone)} – {formatDate(item.end_at, { hour: "2-digit", minute: "2-digit" }, timezone)}</span>
<small>{item.source}</small>
</>}{item.kind === "deadline" && !compact && <small>Deadline · not a meeting</small>}</button>;
                })}</div>;
        })}
  </div>;
}
export function CalendarView({ api, scenarioNow }: {
    api?: AltoApiContext;
    scenarioNow?: string;
}) {
    const [chosenWeek, setWeek] = useState<string | null>(null);
    const week = chosenWeek ?? mondayOf(scenarioNow ?? new Date().toISOString());
    const [chosenDay, setSelectedDay] = useState<string | null>(null);
    const selectedDay = chosenDay ?? week;
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [view, setView] = useState("week");
    const resource = useResource<CalendarData>(api, `/calendar?start=${encodeURIComponent(`${addDays(week, -1)}T00:00:00Z`)}&end=${encodeURIComponent(`${addDays(week, 8)}T00:00:00Z`)}`);
    const timezone = resource.data?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
    const items = resource.data?.items ?? [];
    const selected = items.find((item) => item.id === selectedId);
    const selectedItems = items.filter((item) => dayKey(item.start_at, timezone) === selectedDay).sort((a, b) => a.start_at.localeCompare(b.start_at));
    function move(days: number) { setWeek(addDays(week, days)); setSelectedDay(addDays(selectedDay, days)); setSelectedId(null); }
    return <div className="alto-calendar-page">
<PageHeading title="My calendar" subtitle={<>{formatDate(`${week}T12:00:00Z`, { month: "short", day: "numeric" }, "UTC")} – {formatDate(`${addDays(week, 4)}T12:00:00Z`, { month: "short", day: "numeric", year: "numeric" }, "UTC")} · {timezone}{scenarioNow ? " · Scenario time" : ""}</>} actions={<>
<div className="alto-calendar-nav">
<IconButton icon="left" label="Previous week" onClick={() => move(-7)}/>
<button onClick={() => { const today = mondayOf(scenarioNow ?? new Date().toISOString()); setWeek(today); setSelectedDay(dayKey(scenarioNow ?? new Date().toISOString(), timezone)); setSelectedId(null); }}>Today</button>
<IconButton icon="right" label="Next week" onClick={() => move(7)}/>
</div>
<select aria-label="Calendar view" value={view} onChange={(event) => setView(event.target.value)}>
<option value="week">Week</option>
<option value="agenda">Agenda</option>
</select>
</>}/>{resource.loading && <Loading />}<ErrorNotice error={resource.error} retry={resource.refresh}/>
<div className="alto-calendar-layout">
<div>{view === "week" ? <CalendarGrid items={items} timezone={timezone} week={week} selectedId={selectedId} selectedDay={selectedDay} onDay={(day) => { setSelectedDay(day); setSelectedId(null); }} onSelect={(item) => { setSelectedId(item.id); setSelectedDay(dayKey(item.start_at, timezone)); }}/> : <div className="alto-agenda">{items.filter((item) => dayKey(item.start_at, timezone) >= week && dayKey(item.start_at, timezone) <= addDays(week, 6)).map((item) => <button className={`alto-agenda-item ${item.kind}`} key={item.id} onClick={() => setSelectedId(item.id)}>
<strong>{item.title}</strong>
<span>{dateTime(item.start_at, timezone)} – {dateTime(item.end_at, timezone)}</span>
<small>{humanize(item.kind)} · {item.source}</small>
</button>)}</div>}<div className="alto-calendar-legend">
<span>
<i className="meeting"/>External meeting</span>
<span>
<i className="work"/>ALTO active work</span>
<span>
<i className="protected"/>Protected time</span>
<span>
<Icon name="flag" size={16}/>Deadline marker</span>
</div>
<div className="alto-button-row">{resource.data?.sources.map((source) => <Badge key={source.name}>{source.name} · {humanize(source.status)}</Badge>)}</div>
</div>
<aside className="alto-calendar-inspector">{selected ? <>
<header>
<Badge>{humanize(selected.kind)}</Badge>
<IconButton icon="close" label="Close selected calendar item" onClick={() => setSelectedId(null)}/>
</header>
<h2>{selected.title}</h2>
<p>{dateTime(selected.start_at, timezone)} – {dateTime(selected.end_at, timezone)}</p>
<p>{selected.source} · {humanize(selected.status)}</p>{selected.kind === "deadline" && <div className="alto-info-banner">This is a deadline marker, not a meeting or an active-work reservation.</div>}<p>{selected.description}</p>{selected.owner_name && <p>
<Icon name="people"/> {selected.owner_name}</p>}{selected.task_id && <button className="alto-text-button" onClick={() => navigate(`/tasks/${selected.task_id}`)}>Open task and submission →</button>}{selected.project_id && <button className="alto-text-button" onClick={() => navigate(`/projects/${selected.project_id}/graph`)}>View in project →</button>}</> : <>
<h2>{formatDate(`${selectedDay}T12:00:00Z`, { weekday: "long", month: "long", day: "numeric" }, "UTC")}</h2>
<p>{selectedItems.length} permitted items</p>{selectedItems.map((item) => <button className={`alto-agenda-item ${item.kind}`} key={item.id} onClick={() => setSelectedId(item.id)}>
<strong>{item.title}</strong>
<span>{formatDate(item.start_at, { hour: "2-digit", minute: "2-digit" }, timezone)} – {formatDate(item.end_at, { hour: "2-digit", minute: "2-digit" }, timezone)}</span>
<small>{humanize(item.kind)} · {item.source}</small>
<Icon name="right" size={16}/>
</button>)}{!selectedItems.length && <p className="alto-muted">No commitments in this projection.</p>}</>}</aside>
</div>
</div>;
}
export function PeopleDirectory({ api }: {
    api?: AltoApiContext;
}) {
    const resource = useResource<{
        people: Person[];
    }>(api, "/people");
    const [search, setSearch] = useState("");
    const [group, setGroup] = useState("all");
    const people = resource.data?.people.filter((person) => (group === "all" || person.operating_group === group) && `${person.display_name} ${person.job_title} ${person.function}`.toLowerCase().includes(search.toLowerCase())) ?? [];
    return <div>
<PageHeading title="People" subtitle="Skills, accepted experience and shared preferences."/>
<div className="alto-list-toolbar">
<div className="alto-tabs">{["all", "Product", "Software"].map((value) => <button key={value} className={group === value ? "active" : ""} onClick={() => setGroup(value)}>{value === "all" ? "Everyone" : value}</button>)}</div>
<label className="alto-search">
<Icon name="search"/>
<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search people…" aria-label="Search people"/>
</label>
</div>{resource.loading && <Loading />}<ErrorNotice error={resource.error} retry={resource.refresh}/>
<div className="alto-people-grid">{people.map((person) => <button key={person.id} className="alto-person-card" onClick={() => navigate(`/people/${person.id}`)}>
<span className="alto-avatar">{initials(person.display_name)}</span>
<div>
<strong>{person.display_name}</strong>
<span>{person.job_title}</span>
<small>{person.operating_group} · {person.function}</small>
<Badge>{person.profile_depth === "rich" ? "Detailed profile" : "Directory profile"}</Badge>
</div>
<Icon name="right"/>
</button>)}</div>{!resource.loading && !people.length && <EmptyState title={search ? "No matching people" : "No people available"}>Only people you are permitted to view appear here.</EmptyState>}</div>;
}
export function PersonProfile({ api, personId, self = false }: {
    api?: AltoApiContext;
    personId: string | null;
    self?: boolean;
}) {
    const resource = useResource<Person>(api, personId ? `/people/${encodeURIComponent(personId)}` : null);
    const command = useCommand();
    const [editing, setEditing] = useState(false);
    const [skills, setSkills] = useState("");
    const [weekOffset, setWeekOffset] = useState(0);
    const person = resource.data;
    if (resource.loading)
        return <Loading />;
    if (resource.error && !resource.data)
        return <ErrorNotice error={resource.error} retry={resource.refresh}/>;
    if (!person)
        return <EmptyState title={self ? "Your profile is not linked yet" : "Person unavailable"}>Your workspace may need an employee profile or a permitted demo actor.</EmptyState>;
    const week = addDays(mondayOf(person.availability[0]?.start_at ?? new Date().toISOString()), weekOffset * 7);
    return <div className="alto-composer-page">
<ErrorNotice error={resource.error} retry={resource.refresh}/>
<PageHeading eyebrow={!self ? <button className="alto-text-button" onClick={() => navigate("/people")}>People / {person.display_name}</button> : undefined} title={self ? "My profile" : <>
<span className="alto-avatar large">{initials(person.display_name)}</span>{person.display_name}</>} subtitle={`${self ? `${person.display_name} · ` : ""}${person.job_title} · ${person.function}`}/>
<div className="alto-profile-grid">
<section className="alto-profile-card">
<header>
<span className="alto-category-icon mint">
<Icon name="settings"/>
</span>
<h2>Skills</h2>{self && <button className="alto-text-button" onClick={() => { setSkills(person.skills.filter((skill) => skill.provenance === "self_declared").map((skill) => skill.name).join(", ")); setEditing(true); }}>Edit</button>}</header>
<div className="alto-skill-tags">{person.skills.map((skill) => <span key={`${skill.name}:${skill.provenance}`} title={`Provenance: ${humanize(skill.provenance)}`}>{skill.name}<small>{humanize(skill.provenance)}</small>
</span>)}</div>{!person.skills.length && <p className="alto-muted">No declared skills yet.</p>}</section>
<section className="alto-profile-card">
<header>
<span className="alto-category-icon peach">
<Icon name="document"/>
</span>
<h2>Past projects</h2>
</header>{person.past_projects.map((project) => <button className="alto-profile-project" key={project.id} onClick={() => navigate(`/projects/${project.id}/graph`)}>
<span>{project.title}<small>Accepted · {formatDate(project.accepted_at)}</small>
</span>
<Badge tone="mint">✓ Completed</Badge>
</button>)}{!person.past_projects.length && <p className="alto-muted">Accepted experience will appear here.</p>}</section>
<section className="alto-profile-card">
<header>
<span className="alto-category-icon rose">
<Icon name="projects"/>
</span>
<h2>Ongoing projects</h2>
</header>{person.ongoing_projects.map((project) => <button className="alto-profile-project" key={project.id} onClick={() => navigate(`/projects/${project.id}/graph`)}>
<span>{project.title}<small>{humanize(project.status)} · Due {formatDate(project.deadline)}</small>
</span>
<Icon name="right"/>
</button>)}{!person.ongoing_projects.length && <p className="alto-muted">No disclosed ongoing projects.</p>}{person.shared_preferences.length > 0 && <section className="alto-shared-preferences">
<h3>Explicitly shared preferences</h3>{person.shared_preferences.map((preference) => <p key={preference.id}>{preference.text}<small>Shared {formatDate(preference.shared_at)}</small>
</p>)}</section>}</section>
<section className="alto-profile-card">
<header>
<span className="alto-category-icon amber">
<Icon name="calendar"/>
</span>
<h2>Availability</h2>
<IconButton icon="left" label="Previous availability week" onClick={() => setWeekOffset((value) => value - 1)}/>
<IconButton icon="right" label="Next availability week" onClick={() => setWeekOffset((value) => value + 1)}/>
</header>
<p className="alto-caption">{formatDate(`${week}T12:00:00Z`)} – {formatDate(`${addDays(week, 4)}T12:00:00Z`)} · {person.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone} · Busy/free only</p>
<CalendarGrid compact items={person.availability} week={week} timezone={person.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}/>
</section>
</div>
{self && api && <details className="alto-private-details"><summary>Private feedback & preference history</summary><PrivateFeedback api={api}/></details>}
<Assistant api={api} context={{ kind: "person", id: person.id, label: person.display_name }} placeholder="Ask ALTO about this profile…"/>{editing && <Modal title="Edit your declared skills" onClose={() => setEditing(false)}>
<p>Accepted experience and confirmed qualifications cannot be overwritten here. Updates affect future planning only.</p>
<label className="alto-field">Skills, separated by commas<textarea rows={4} value={skills} maxLength={2000} onChange={(event) => setSkills(event.target.value)}/>
</label>
<button className="alto-primary" disabled={command.busy} onClick={() => void command.run(async () => { if (!api)
        return; await altoRequest(api, "/me/profile", { method: "PATCH", body: { expected_row_version: person.row_version, skills: skills.split(",").map((value) => value.trim()).filter(Boolean) } }); setEditing(false); resource.refresh(); })}>Save declarations</button>
<ErrorNotice error={command.error}/>
</Modal>}</div>;
}
