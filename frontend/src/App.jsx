import { useEffect, useState } from 'react'
import {
  Activity, ArrowRight, BarChart3, Camera, CheckCircle2, ChevronDown, ChevronRight, Clock3,
  DoorOpen, Fingerprint, FlaskConical, History, Info, LayoutDashboard, Layers, MapPin,
  Moon, Play, Radio, Save, ScanLine, Send, Shield, ShieldAlert, ShieldCheck, SlidersHorizontal,
  Sun, SunMoon, Thermometer, Timer, Trash2, TriangleAlert, WifiOff, XCircle,
} from 'lucide-react'

/* ---------- formatting ---------- */
const time = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Toronto', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
const dateTime = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Toronto', dateStyle: 'medium', timeStyle: 'short',
})
const percent = value => value == null ? '—' : new Intl.NumberFormat('en-CA', {
  style: 'percent', maximumFractionDigits: 1,
}).format(value)
const seconds = (later, earlier) => Math.round((new Date(later) - new Date(earlier)) / 1000)

/* ---------- vocabulary ---------- */
const names = {
  camera_offline: 'Camera offline', camera_online: 'Camera restored',
  controller_offline: 'Controller unavailable', access_granted: 'Access granted',
  access_denied: 'Access denied', door_open: 'Door opened', forced_door: 'Forced door opening',
  unauthorized_open: 'Unverified door opening', motion_detected: 'Motion detected',
  temperature_warning: 'Temperature warning',
}
const sources = {
  camera: Camera, controller: WifiOff, access: Fingerprint,
  door: DoorOpen, motion: ScanLine, environment: Thermometer,
}
const attentionKinds = new Set([
  'camera_offline', 'controller_offline', 'access_denied', 'forced_door',
  'unauthorized_open', 'temperature_warning',
])
const navigation = [
  ['overview', 'Overview', LayoutDashboard], ['simulate', 'Simulate', Send],
  ['history', 'Run history', History], ['rules', 'Correlation rules', SlidersHorizontal],
  ['evaluation', 'Evaluation', BarChart3],
]
const headings = {
  overview: ['Security overview', 'Watch raw sensor events become correlated incidents, live or from a saved run.'],
  simulate: ['Simulate', 'Send individual sensor events to the live session, replay a fixed scenario, or reset stored data.'],
  history: ['Run history', 'Reopen previous simulations with their full evidence and incidents.'],
  rules: ['Correlation rules', 'Ordered event sequences, time windows, and zone constraints currently in force.'],
  evaluation: ['Evaluation', 'How the rule engine performs against the fixed scenario suite.'],
}
const screen = () => navigation.some(([id]) => location.hash === '#' + id)
  ? location.hash.slice(1) : 'overview'
const LIVE_POLL_MS = 2000
const scenarioName = (scenarios, id) => id === 'live' ? 'Live session'
  : scenarios.find(item => item.id === id)?.name ?? id

/* ---------- theme ---------- */
const themes = [['system', 'System', SunMoon], ['light', 'Light', Sun], ['dark', 'Dark', Moon]]
const readTheme = () => {
  const override = new URLSearchParams(location.search).get('theme')
  if (themes.some(([id]) => id === override)) return override
  try { return localStorage.getItem('theme') || 'system' } catch { return 'system' }
}
function applyTheme(choice) {
  const dark = choice === 'dark' || (choice === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

/* ---------- api ---------- */
async function api(path, options) {
  const response = await fetch('/api/' + path, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The request could not be completed.')
  }
  return response.json()
}

/* ---------- primitives ---------- */
function IconTile({ icon: Icon, tone = '' }) {
  return <span className={'icon-tile ' + tone}><Icon size={16} aria-hidden="true" /></span>
}

function Severity({ value }) {
  return <span className={'severity sev-' + value}><span className="dot" />{value}</span>
}

function Tag({ icon: Icon, children }) {
  return <span className="tag">{Icon && <Icon size={12} aria-hidden="true" />}{children}</span>
}

function Stat({ icon, title, value, detail, tone }) {
  return <article className="panel stat">
    <div className="stat-label"><span>{title}</span><IconTile icon={icon} tone={tone} /></div>
    <div><strong>{value}</strong><small className="block">{detail}</small></div>
  </article>
}

function Empty({ icon: Icon = Info, title, children }) {
  return <div className="empty"><Icon size={22} aria-hidden="true" /><strong>{title}</strong><p>{children}</p></div>
}

function Skeleton() {
  return <div className="space-y-5" role="status" aria-label="Loading simulation data">
    <div className="skeleton h-20" /><div className="skeleton h-28" />
    <div className="overview-grid"><div className="skeleton h-96" /><div className="skeleton h-96" /></div>
  </div>
}

/* ---------- overview ---------- */
function SourceSwitch({ source, setSource, live, saved }) {
  return <div className="segmented" role="group" aria-label="Data source">
    <button type="button" aria-pressed={source === 'live'} onClick={() => setSource('live')}>
      <Radio size={13} aria-hidden="true" />Live session · {live?.event_count ?? 0}
    </button>
    <button type="button" aria-pressed={source === 'saved'} onClick={() => setSource('saved')} disabled={!saved}>
      <History size={13} aria-hidden="true" />Saved run
    </button>
  </div>
}

function Funnel({ run }) {
  const reduction = run.raw_alert_count ? 1 - run.incident_count / run.raw_alert_count : 0
  return <section className="funnel" aria-label="Alert correlation summary">
    <div>
      <span className="label">Sensor events</span>
      <span className="value">{run.event_count}</span>
      <span className="hint">{run.duplicate_count ? run.duplicate_count + ' duplicate messages discarded' : 'Normalized, unique, time-ordered'}</span>
      <span className="step-arrow"><ChevronRight size={14} aria-hidden="true" /></span>
    </div>
    <div>
      <span className="label">Standalone alerts</span>
      <span className="value">{run.raw_alert_count}</span>
      <span className="hint">Baseline: one alert per eligible event</span>
      <span className="step-arrow"><ChevronRight size={14} aria-hidden="true" /></span>
    </div>
    <div className="reduction">
      <span className="label">Correlated incidents</span>
      <span className="value">{run.incident_count}</span>
      <span className="hint">{run.raw_alert_count ? percent(reduction) + ' fewer alerts for the operator' : 'No alert-eligible events'}</span>
    </div>
  </section>
}

function EventFeed({ events, evidenceIds, focusIds }) {
  const [filter, setFilter] = useState('all')
  const ordered = [...events].reverse()
  const visible = ordered.filter(event => filter === 'all' || evidenceIds.has(event.id))
  return <section className="panel" aria-labelledby="feed-heading">
    <div className="panel-heading">
      <div><h3 id="feed-heading">Sensor event feed</h3><p>Newest first · Toronto time</p></div>
      <div className="segmented" role="group" aria-label="Filter events">
        <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>All · {events.length}</button>
        <button type="button" aria-pressed={filter === 'evidence'} onClick={() => setFilter('evidence')}>Evidence · {evidenceIds.size}</button>
      </div>
    </div>
    <div className="feed-columns" aria-hidden="true"><span>Time</span><span>Event · device</span><span>Zone</span><span className="text-right">Role</span></div>
    {visible.length ? <ol className="event-list">
      {visible.map(event => {
        const evidence = evidenceIds.has(event.id)
        const tone = event.kind === 'forced_door' ? 'critical' : attentionKinds.has(event.kind) ? 'warn' : 'neutral'
        const className = 'event-row' + (evidence ? ' is-evidence' : '') + (focusIds.has(event.id) ? ' is-focus' : '')
        return <li className={className} key={event.id}>
          <time className="event-time" dateTime={event.occurred_at}>{time.format(new Date(event.occurred_at))}</time>
          <div className="event-identity">
            <IconTile icon={sources[event.source] ?? Activity} tone={tone} />
            <div><strong>{names[event.kind] ?? event.kind}</strong><small>{event.device_id}</small></div>
          </div>
          <span className="event-zone">{event.zone}{event.restricted ? ' · restricted' : ''}</span>
          {evidence && <span className="event-flag">Evidence</span>}
        </li>
      })}
    </ol> : <Empty title="No matching events">Switch the filter to see every event in this run.</Empty>}
    <p className="feed-footer"><span>{visible.length} of {events.length} events shown</span><span>Evidence rows are marked on the left edge</span></p>
  </section>
}

function IncidentCard({ incident, rules, onFocus }) {
  const first = incident.evidence[0].occurred_at
  const span = seconds(incident.occurred_at, first)
  const primary = rules.find(rule => rule.id === incident.rule_ids[0])
  const window = primary?.window_seconds
  const title = id => rules.find(rule => rule.id === id)?.title ?? id
  const ids = incident.evidence.map(event => event.id)
  return <article className={'incident sev-' + incident.severity}
    onMouseEnter={() => onFocus(ids)} onMouseLeave={() => onFocus([])}
    onFocus={() => onFocus(ids)} onBlur={() => onFocus([])}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Severity value={incident.severity} /><span className="incident-id">{incident.id}</span>
    </div>
    <h4>{incident.title}</h4>
    <div className="incident-meta">
      <Tag icon={MapPin}>{incident.zone}</Tag>
      <Tag icon={Timer}>{span}s span</Tag>
      <Tag icon={Layers}>{incident.evidence.length} events</Tag>
    </div>
    <h5>Evidence timeline{window && <span>{span}s of {window}s window</span>}</h5>
    {window && <div className="window-bar" role="img" aria-label={`Sequence completed in ${span} of ${window} seconds`}>
      <div style={{ width: Math.min(100, Math.round(span / window * 100)) + '%' }} />
    </div>}
    <ol className="timeline">
      {incident.evidence.map(event => <li key={event.id}>
        <div>{names[event.kind] ?? event.kind}<small>{event.device_id}</small></div>
        <time dateTime={event.occurred_at}>{time.format(new Date(event.occurred_at))}<b>+{seconds(event.occurred_at, first)}s</b></time>
      </li>)}
    </ol>
    <details className="rule-matches">
      <summary>{incident.rule_ids.length} matched {incident.rule_ids.length === 1 ? 'rule' : 'rules'}<ChevronDown size={15} aria-hidden="true" /></summary>
      <ul>{incident.rule_ids.map(id => <li key={id}><Tag icon={SlidersHorizontal}>{title(id)}</Tag></li>)}</ul>
    </details>
  </article>
}

function Overview({ run, rules, live }) {
  const [focusIds, setFocusIds] = useState(new Set())
  if (!run || (live && !run.events.length)) return <div className="panel"><Empty icon={live ? Radio : FlaskConical} title={live ? 'Waiting for live events' : 'No simulation yet'}>
    {live ? 'Events sent from the Simulate tab, on any device on this network, appear here within a couple of seconds.' : 'Open the Simulate tab to replay a scenario or start a live session.'}
    <a className="btn btn-primary btn-sm mt-4" href="#simulate"><Send size={14} aria-hidden="true" />Open Simulate</a>
  </Empty></div>
  const { events, incidents } = run
  const evidenceIds = new Set(incidents.flatMap(incident => incident.evidence.map(event => event.id)))
  return <>
    <Funnel run={run} />
    <div className="overview-grid">
      <section className="panel" aria-labelledby="incidents-heading">
        <div className="panel-heading">
          <div><h3 id="incidents-heading">Correlated incidents</h3><p>Hover an incident to highlight its evidence in the feed</p></div>
          <span className="count">{incidents.length}</span>
        </div>
        {incidents.length ? <div className="incident-list">
          {[...incidents].reverse().map(incident => <IncidentCard key={incident.id} incident={incident} rules={rules} onFocus={ids => setFocusIds(new Set(ids))} />)}
        </div> : <Empty icon={ShieldCheck} title="No correlated incidents">No event sequence met the configured rules in this run.</Empty>}
      </section>
      <EventFeed events={events} evidenceIds={evidenceIds} focusIds={focusIds} />
    </div>
  </>
}

/* ---------- simulate ---------- */
function LiveSender({ choices, live, busy, onSend, onClear, onSave }) {
  const [zone, setZone] = useState('server')
  const [signal, setSignal] = useState('camera:link_down')
  const [log, setLog] = useState([])
  const zoneInfo = choices.zones.find(item => item.id === zone)
  async function send(payload) {
    const result = await onSend(payload)
    if (result) setLog(previous => [{ ...result, key: result.event.id }, ...previous].slice(0, 8))
  }
  function submit(event) {
    event.preventDefault()
    const [system, code] = signal.split(':')
    send({ location: zone, system, signal: code })
  }
  return <section className="panel" aria-labelledby="live-heading">
    <div className="panel-heading">
      <div><h3 id="live-heading">Live event sender</h3><p>Each event is normalized, correlated, and shown on the Overview within {LIVE_POLL_MS / 1000}s</p></div>
      <span className="status-pill live"><span className="pulse" aria-hidden="true" />{live?.event_count ?? 0} events · {live?.incident_count ?? 0} incidents</span>
    </div>
    <form className="sender" onSubmit={submit}>
      <div className="field">
        <label htmlFor="live-zone">Zone</label>
        <div className="select-wrap">
          <select id="live-zone" value={zone} onChange={event => setZone(event.target.value)}>
            {choices.zones.map(item => <option key={item.id} value={item.id}>{item.name}{item.restricted ? ' (restricted)' : ''}</option>)}
          </select><ChevronDown size={15} aria-hidden="true" />
        </div>
      </div>
      <div className="field">
        <label htmlFor="live-signal">Sensor event</label>
        <div className="select-wrap">
          <select id="live-signal" value={signal} onChange={event => setSignal(event.target.value)}>
            {choices.signals.map(item => <option key={item.system + ':' + item.signal} value={item.system + ':' + item.signal}>{item.label}</option>)}
          </select><ChevronDown size={15} aria-hidden="true" />
        </div>
      </div>
      <button className="btn btn-primary" type="submit" disabled={busy}><Send size={15} aria-hidden="true" />Send event</button>
    </form>
    <div className="quick-send">
      <span className="section-label">Quick send to {zoneInfo?.name}</span>
      <div className="quick-grid">
        {choices.signals.filter(item => attentionKinds.has(item.kind) || item.kind === 'door_open').map(item => {
          const Icon = sources[item.system] ?? Activity
          const tone = item.kind === 'forced_door' ? 'critical' : attentionKinds.has(item.kind) ? 'warn' : 'neutral'
          return <button key={item.kind} type="button" className="quick" disabled={busy}
            onClick={() => send({ location: zone, system: item.system, signal: item.signal })}>
            <IconTile icon={Icon} tone={tone} />{item.label}
          </button>
        })}
      </div>
    </div>
    {log.length > 0 && <ol className="send-log" aria-label="Recently sent events">
      {log.map(entry => <li key={entry.key} className={entry.new_incident ? 'sev-' + entry.new_incident.severity : ''}>
        <time className="event-time" dateTime={entry.event.occurred_at}>{time.format(new Date(entry.event.occurred_at))}</time>
        <span><strong>{names[entry.event.kind] ?? entry.event.kind}</strong> · {entry.event.zone}</span>
        {entry.new_incident ? <span className="severity"><span className="dot" />{entry.new_incident.severity} incident</span> : <span className="tag">Sent</span>}
      </li>)}
    </ol>}
    <div className="feed-footer">
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !live?.event_count} onClick={onSave}><Save size={14} aria-hidden="true" />Save session as run</button>
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !live?.event_count} onClick={onClear}><Trash2 size={14} aria-hidden="true" />Clear live session</button>
    </div>
  </section>
}

function ScenarioReplay({ scenarios, selected, setSelected, busy, onRun }) {
  const scenario = scenarios.find(item => item.id === selected)
  return <section className="panel" aria-labelledby="replay-heading">
    <div className="panel-heading"><div><h3 id="replay-heading">Replay a fixed scenario</h3><p>Runs a reproducible batch and saves it to Run history</p></div></div>
    <form className="sender" onSubmit={onRun}>
      <div className="field">
        <label htmlFor="scenario">Scenario</label>
        <div className="select-wrap">
          <select id="scenario" value={selected} onChange={event => setSelected(event.target.value)} disabled={!scenarios.length || busy}>
            {scenarios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select><ChevronDown size={15} aria-hidden="true" />
        </div>
      </div>
      <button className="btn btn-secondary" type="submit" disabled={!selected || busy}><Play size={15} aria-hidden="true" />{busy ? 'Running…' : 'Run scenario'}</button>
    </form>
    {scenario && <p className="scenario-desc px-4 pb-4 sm:px-5"><Info size={15} aria-hidden="true" /><span>{scenario.description}</span></p>}
  </section>
}

function DataReset({ runs, busy, onReset }) {
  const [armed, setArmed] = useState(false)
  return <section className="panel" aria-labelledby="reset-heading">
    <div className="panel-heading"><div><h3 id="reset-heading">Reset stored data</h3><p>Deletes every saved run, including the seeded demonstration. The live session and rules are unaffected.</p></div></div>
    <div className="feed-footer">
      <span>{runs.length} saved {runs.length === 1 ? 'run' : 'runs'}</span>
      {armed ? <span className="flex gap-2">
        <button type="button" className="btn btn-danger btn-sm" disabled={busy} onClick={async () => { await onReset(); setArmed(false) }}><Trash2 size={14} aria-hidden="true" />Yes, delete all runs</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setArmed(false)}>Cancel</button>
      </span> : <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !runs.length} onClick={() => setArmed(true)}><Trash2 size={14} aria-hidden="true" />Delete all saved runs</button>}
    </div>
  </section>
}

/* ---------- history ---------- */
function RunHistory({ runs, scenarios, onOpen, busy, currentId }) {
  return <section className="panel" aria-labelledby="history-heading">
    <div className="panel-heading"><div><h3 id="history-heading">Saved runs</h3><p>Most recent 20 simulations, stored with their full evidence</p></div></div>
    {runs.length ? <>
      <div className="data-head history-cols" aria-hidden="true"><span>Scenario</span><span>Recorded</span><span>Events</span><span>Incidents</span><span>Outcome</span><span /></div>
      <ul>
        {runs.map(run => <li key={run.id} className="data-row history-cols">
          <div><strong>{scenarioName(scenarios, run.scenario_id)}</strong>
            <span className="incident-id">{run.id}</span></div>
          <span className="outcome-text"><span className="cell-label">Recorded</span>{dateTime.format(new Date(run.created_at))}</span>
          <span className="num"><span className="cell-label">Events</span>{run.event_count}</span>
          <span className="num"><span className="cell-label">Incidents</span>{run.incident_count}</span>
          <span><span className={'result ' + (run.passed ? 'passed' : 'failed')}>{run.passed ? 'Expected' : 'Unexpected'}</span></span>
          <button type="button" className="btn btn-secondary btn-sm justify-self-start sm:justify-self-end" disabled={busy} onClick={() => onOpen(run.id)}>
            {run.id === currentId ? 'Viewing' : 'Open'} <ArrowRight size={14} aria-hidden="true" />
          </button>
        </li>)}
      </ul>
    </> : <Empty icon={History} title="No saved runs">Simulations appear here as soon as you run one.</Empty>}
  </section>
}

/* ---------- rules ---------- */
function Rules({ rules }) {
  return <div className="rules-grid">
    {rules.map(rule => <article className="panel rule-card" key={rule.id}>
      <div className="flex flex-wrap items-start justify-between gap-2"><h3>{rule.title}</h3><Severity value={rule.severity} /></div>
      <p>{rule.description}</p>
      <ol className="rule-chain" aria-label="Required event sequence">
        {rule.sequence.map((kind, index) => <li key={index} className="contents">
          {index > 0 && <ChevronRight size={14} aria-hidden="true" />}
          <span className="rule-step"><i>{index + 1}</i>{names[kind] ?? kind}</span>
        </li>)}
      </ol>
      <div className="rule-constraints">
        <Tag icon={Timer}>{rule.window_seconds}s window</Tag>
        <Tag icon={MapPin}>Same zone</Tag>
        {rule.restricted_only && <Tag icon={Shield}>Restricted area</Tag>}
        {rule.after_hours_only && <Tag icon={Clock3}>After staffed hours</Tag>}
      </div>
    </article>)}
  </div>
}

/* ---------- evaluation ---------- */
function Evaluation({ report, rules }) {
  if (!report) return <Skeleton />
  const title = id => rules.find(rule => rule.id === id)?.title ?? id
  const outcomes = ids => ids.length ? ids.map(title).join(', ') : 'No incident'
  return <>
    <div className="stats">
      <Stat icon={CheckCircle2} title="Scenarios passed" value={report.passed + '/' + report.total} detail="Actual primary rules match the expectation" tone="ok" />
      <Stat icon={Shield} title="Detection rate" value={percent(report.detection_rate)}
        detail={report.true_positives + ' of ' + (report.true_positives + report.false_negatives) + ' positive scenarios detected'} />
      <Stat icon={TriangleAlert} title="False-positive rate" value={percent(report.false_positive_rate)}
        detail={report.false_positives + ' of ' + (report.false_positives + report.true_negatives) + ' negative scenarios flagged'} tone="warn" />
      <Stat icon={Layers} title="Alert reduction" value={percent(report.alert_reduction)}
        detail={report.raw_alerts + ' standalone alerts become ' + report.incidents + ' incidents'} />
    </div>
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <section className="panel" aria-labelledby="matrix-heading">
        <div className="panel-heading"><div><h3 id="matrix-heading">Confusion matrix</h3><p>Scenario-level incident presence</p></div></div>
        <div className="matrix">
          <span className="corner" /><span className="axis">Incident raised</span><span className="axis">No incident</span>
          <span className="axis rows">Should alert</span>
          <div className="cell good"><span>True positives</span><strong>{report.true_positives}</strong></div>
          <div className="cell bad"><span>False negatives</span><strong>{report.false_negatives}</strong></div>
          <span className="axis rows">Benign</span>
          <div className="cell bad"><span>False positives</span><strong>{report.false_positives}</strong></div>
          <div className="cell good"><span>True negatives</span><strong>{report.true_negatives}</strong></div>
        </div>
      </section>
      <section className="panel" aria-labelledby="results-heading">
        <div className="panel-heading"><div><h3 id="results-heading">Scenario results</h3><p>Calculated from the current rules and the fixed synthetic suite</p></div>
          <span className="count">{report.total}</span></div>
        <div className="data-head eval-cols" aria-hidden="true"><span>Scenario</span><span>Expected</span><span>Actual</span><span className="text-right">Result</span></div>
        <ul>
          {report.scenarios.map(row => <li className="data-row eval-cols" key={row.scenario.id}>
            <strong>{row.scenario.name}</strong>
            <span className="outcome-text"><span className="cell-label">Expected</span>{outcomes(row.scenario.expected_rules)}</span>
            <span className="outcome-text"><span className="cell-label">Actual</span>{outcomes(row.actual_rules)}</span>
            <span className="sm:text-right"><span className={'result ' + (row.passed ? 'passed' : 'failed')}>
              {row.passed ? <CheckCircle2 size={13} aria-hidden="true" /> : <XCircle size={13} aria-hidden="true" />}{row.passed ? 'Passed' : 'Failed'}
            </span></span>
          </li>)}
        </ul>
      </section>
    </div>
  </>
}

/* ---------- app ---------- */
export default function App() {
  const [page, setPage] = useState(screen)
  const [theme, setTheme] = useState(readTheme)
  const [scenarios, setScenarios] = useState([])
  const [rules, setRules] = useState([])
  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null)
  const [report, setReport] = useState(null)
  const [selected, setSelected] = useState('')
  const [ready, setReady] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [live, setLive] = useState(null)
  const [choices, setChoices] = useState(null)
  const [source, setSource] = useState(null)

  useEffect(() => {
    const change = () => setPage(screen())
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])

  useEffect(() => {
    applyTheme(theme)
    try { localStorage.setItem('theme', theme) } catch { /* storage unavailable */ }
    const media = matchMedia('(prefers-color-scheme: dark)')
    const sync = () => theme === 'system' && applyTheme(theme)
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [theme])

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [available, configured, recent, evaluation, liveChoices, liveState] = await Promise.all([
          api('scenarios'), api('rules'), api('runs'), api('evaluation'), api('live/options'), api('live'),
        ])
        const latest = recent.length ? await api('runs/' + recent[0].id) : null
        if (!active) return
        setScenarios(available)
        setRules(configured)
        setRuns(recent)
        setReport(evaluation)
        setChoices(liveChoices)
        setLive(liveState)
        setRun(latest)
        setSelected(latest?.scenario_id ?? available[0]?.id ?? '')
        setReady(true)
      } catch (failure) {
        if (active) setError('Could not load the security console. ' + failure.message)
      }
    }
    load()
    return () => { active = false }
  }, [attempt])

  useEffect(() => {
    if (!ready || (page !== 'overview' && page !== 'simulate')) return
    let active = true
    const tick = async () => {
      try {
        const state = await api('live')
        if (active) setLive(previous => previous?.version === state.version ? previous : state)
      } catch { /* keep the last known state */ }
    }
    const timer = setInterval(tick, LIVE_POLL_MS)
    return () => { active = false; clearInterval(timer) }
  }, [ready, page])

  async function sendLiveEvent(payload) {
    setError('')
    try {
      const result = await api('live/events', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })
      setLive(await api('live'))
      return result
    } catch (failure) {
      setError(failure.message)
      return null
    }
  }

  async function clearLive() {
    setError('')
    try {
      await api('live', { method: 'DELETE' })
      setLive(await api('live'))
      setStatus('Live session cleared.')
    } catch (failure) { setError(failure.message) }
  }

  async function saveLive() {
    setBusy(true)
    setError('')
    try {
      const result = await api('live/save', { method: 'POST' })
      setRuns(previous => [result, ...previous].slice(0, 20))
      setStatus('Live session saved to Run history.')
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }

  async function resetRuns() {
    setBusy(true)
    setError('')
    try {
      const result = await api('runs', { method: 'DELETE' })
      setRuns([])
      setRun(null)
      setStatus(result.deleted + ' saved runs deleted.')
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }

  async function runSimulation(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const result = await api('runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: selected }),
      })
      setRun(result)
      setSource('saved')
      setRuns(previous => [result, ...previous].slice(0, 20))
      setStatus('Scenario complete: ' + result.event_count + ' events produced ' + result.incident_count + ' correlated ' + (result.incident_count === 1 ? 'incident.' : 'incidents.'))
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  async function openRun(id) {
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const result = await api('runs/' + id)
      setRun(result)
      setSource('saved')
      if (result.scenario_id !== 'live') setSelected(result.scenario_id)
      location.hash = 'overview'
      setStatus('Saved simulation opened.')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  const liveRun = live?.run ?? null
  const activeSource = source ?? (liveRun?.event_count ? 'live' : 'saved')
  const shown = activeSource === 'live' ? liveRun : run
  const [title, subtitle] = headings[page]
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => {
      event.preventDefault()
      document.getElementById('main-content').focus()
    }}>Skip to content</a>
    <aside className="sidebar">
      <a href="#overview" className="brand"><span className="brand-mark"><Shield size={19} aria-hidden="true" /></span>
        <span>Building Security<small>INSE 6680 console</small></span>
      </a>
      <div className="nav-group">
        <span className="nav-label">Workspace</span>
        <nav aria-label="Main navigation">
          {navigation.map(([id, label, Icon]) => <a href={'#' + id} key={id} aria-current={page === id ? 'page' : undefined}>
            <Icon size={17} aria-hidden="true" />{label}
          </a>)}
        </nav>
      </div>
      <div className="sidebar-footer">
        <span className="env-chip"><FlaskConical size={14} aria-hidden="true" />Synthetic devices · local only</span>
        <div className="segmented" role="group" aria-label="Colour theme">
          {themes.map(([id, label, Icon]) => <button key={id} type="button" aria-pressed={theme === id} onClick={() => setTheme(id)} title={label}>
            <Icon size={14} aria-hidden="true" /><span className="sr-only xl:not-sr-only">{label}</span>
          </button>)}
        </div>
      </div>
    </aside>
    <main id="main-content" tabIndex={-1}>
      <header className="topbar">
        <h1>{title}</h1>
        <div className="topbar-tools">
          {page === 'overview' && activeSource === 'saved' && run && <span className="tag"><History size={12} aria-hidden="true" />{scenarioName(scenarios, run.scenario_id)}</span>}
          {page === 'overview' && activeSource === 'live'
            ? <span className="status-pill live"><span className="pulse" aria-hidden="true" /><Radio size={13} aria-hidden="true" />Live · updating every {LIVE_POLL_MS / 1000}s</span>
            : <span className="status-pill"><FlaskConical size={13} aria-hidden="true" />Simulation</span>}
        </div>
      </header>
      <div className="workspace">
        <div className="page-heading"><div><h2>{title}</h2><p>{subtitle}</p></div>
          {ready && page === 'overview' && <SourceSwitch source={activeSource} setSource={setSource} live={liveRun} saved={run} />}
        </div>
        {error && <div className="notice notice-error" role="alert"><span><ShieldAlert size={16} aria-hidden="true" />{error}</span>
          {!ready && <button className="btn btn-secondary btn-sm" onClick={() => {
            setError('')
            setAttempt(previous => previous + 1)
          }}>Retry</button>}
        </div>}
        {status && <div className="notice notice-ok" role="status"><span><CheckCircle2 size={16} aria-hidden="true" />{status}</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setStatus('')}>Dismiss</button>
        </div>}
        {!ready && !error && <Skeleton />}
        {ready && page === 'overview' && <Overview key={activeSource === 'live' ? 'live' : run?.id} run={shown} rules={rules} live={activeSource === 'live'} />}
        {ready && page === 'simulate' && <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <LiveSender choices={choices} live={liveRun} busy={busy} onSend={sendLiveEvent} onClear={clearLive} onSave={saveLive} />
          <div className="space-y-4">
            <ScenarioReplay scenarios={scenarios} selected={selected} setSelected={setSelected} busy={busy} onRun={runSimulation} />
            <DataReset runs={runs} busy={busy} onReset={resetRuns} />
          </div>
        </div>}
        {ready && page === 'history' && <RunHistory runs={runs} scenarios={scenarios} onOpen={openRun} busy={busy} currentId={run?.id} />}
        {ready && page === 'rules' && <Rules rules={rules} />}
        {ready && page === 'evaluation' && <Evaluation report={report} rules={rules} />}
      </div>
    </main>
  </div>
}
