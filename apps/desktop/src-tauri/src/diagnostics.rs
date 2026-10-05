//! Best-effort diagnostics: bounded queues, no file IO on process/pipe threads.
use std::{collections::HashMap, fs::{self, OpenOptions}, io::{self, Read, Write},
    path::PathBuf, sync::{mpsc::{self, SyncSender}, Mutex, OnceLock}, thread,
    time::{Duration, Instant}};

const MAX_BYTES: u64 = 2 * 1024 * 1024;
const MAX_LINE: usize = 8192;
static SHELL: OnceLock<LogSink> = OnceLock::new();
static THROTTLE: OnceLock<Mutex<Throttle>> = OnceLock::new();

#[derive(Clone)]
pub(crate) struct LogSink { sender: SyncSender<Record> }
enum Record { Line(String), Flush(mpsc::Sender<()>) }

impl LogSink {
    pub(crate) fn new(path: PathBuf) -> Self {
        let (sender, receiver) = mpsc::sync_channel::<Record>(256);
        // Failure to start the writer disconnects the queue; callers still never block.
        let _ = thread::Builder::new().name("diagnostic-writer".into()).spawn(move || {
            let mut file = RollingFile { path, max_bytes: MAX_BYTES };
            while let Ok(record) = receiver.recv() {
                match record {
                    Record::Line(line) => { let _ = file.append(&line); }
                    Record::Flush(done) => { let _ = done.send(()); }
                }
            }
        });
        Self { sender }
    }

    pub(crate) fn write(&self, level: &str, message: &str) {
        let message = redact(message);
        let line = format!("{} [{level}] {message}\n", chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true));
        // Full/dropped writer: discard this record, not the child's pipe data.
        let _ = self.sender.try_send(Record::Line(line));
    }

    fn flush(&self) {
        let (sender, receiver) = mpsc::channel();
        if self.sender.try_send(Record::Flush(sender)).is_ok() {
            // A stuck filesystem must never hold application shutdown indefinitely.
            let _ = receiver.recv_timeout(Duration::from_millis(500));
        }
    }
}

pub(crate) fn init(root: &std::path::Path) {
    SHELL.get_or_init(|| LogSink::new(root.join("logs/shell.log")));
}
pub(crate) fn event(level: &str, message: &str) {
    if let Some(log) = SHELL.get() { log.write(level, message); }
}
pub(crate) fn flush() { if let Some(log) = SHELL.get() { log.flush(); } }

#[derive(Default)]
struct Throttle { seen: HashMap<String, Instant> }
impl Throttle {
    fn allow(&mut self, key: &str, now: Instant) -> bool {
        self.seen.retain(|_, at| now.duration_since(*at) < Duration::from_secs(60));
        if self.seen.contains_key(key) { return false; }
        // Bound memory even if errors contain rapidly changing paths.
        if self.seen.len() >= 128 { return false; }
        self.seen.insert(key.to_owned(), now);
        true
    }
}
pub(crate) fn failure(kind: &str, reason: &str, elapsed: Duration) {
    let reason = redact(reason);
    let key = format!("{kind}: {reason}");
    if let Ok(mut throttle) = THROTTLE.get_or_init(|| Mutex::new(Throttle::default())).lock() {
        if throttle.allow(&key, Instant::now()) {
            event("WARN", &format!("{kind} elapsed_ms={} reason={reason}", elapsed.as_millis()));
        }
    }
}

struct RollingFile { path: PathBuf, max_bytes: u64 }
impl RollingFile {
    fn append(&mut self, line: &str) -> io::Result<()> {
        if let Some(parent) = self.path.parent() { fs::create_dir_all(parent)?; }
        let size = fs::metadata(&self.path).map(|m| m.len()).unwrap_or(0);
        if size + line.len() as u64 > self.max_bytes {
            let first = self.path.with_extension("log.1");
            let second = self.path.with_extension("log.2");
            if second.exists() { fs::remove_file(&second)?; }
            if first.exists() { fs::rename(&first, &second)?; }
            if self.path.exists() { fs::rename(&self.path, &first)?; }
        }
        OpenOptions::new().create(true).append(true).open(&self.path)?.write_all(line.as_bytes())
    }
}

// Conservative whole-line suppression is intentional: secrets may contain spaces,
// quotes or arbitrary punctuation. Never attempt to retain a partial credential.
fn redact(text: &str) -> String {
    let lower = text.to_lowercase();
    if ["bearer", "token", "ticket", "cookie", "authorization", "password", "secret",
        "response body", "response_body", "responsebody", "响应体", "descriptor=", "descriptor:"]
        .iter().any(|word| lower.contains(word)) {
        return "[REDACTED sensitive record]".into();
    }
    // Catch unlabeled high-entropy credentials as well as structured dumps.
    if text.split(|c: char| !(c.is_ascii_alphanumeric() || c == '-' || c == '_'))
        .any(|word| word.len() >= 40) {
        return "[REDACTED opaque value]".into();
    }
    text.chars().take(MAX_LINE).map(|c| if c.is_control() { ' ' } else { c }).collect()
}

// Console text is untrusted. Retain only stack locations/exception class and
// standard severity records; suppress unknown text, source lines and HTTP dumps.
fn console_line(text: &str) -> String {
    // Preserve the exception class even when its discarded message contains a secret.
    if let Some((class, _)) = text.trim().split_once(':') {
        if (class.ends_with("Error") || class.ends_with("Exception"))
            && class.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_') {
            return format!("{}: [message suppressed]", redact(class));
        }
    }
    let clean = redact(text);
    if clean.starts_with("[REDACTED") { return clean; }
    let trimmed = clean.trim();
    if trimmed.starts_with("Traceback (most recent call last)") { return trimmed.into(); }
    if trimmed.starts_with("File \"") {
        // Python stack frame path + line number only; never the source expression.
        return trimmed.split(", in ").next().unwrap_or("[stack frame]").into();
    }
    // Even severity-prefixed bodies may contain arbitrary secrets; retain the
    // severity only. Hub's structured operational log owns detailed messages.
    for level in ["INFO", "WARNING", "WARN", "ERROR", "CRITICAL", "DEBUG"] {
        if trimmed.starts_with(level) { return format!("{level}: [console message suppressed]"); }
    }
    "[console content suppressed]".into()
}

pub(crate) fn drain(reader: impl Read + Send + 'static, sink: LogSink, pid: u32, stream: &'static str) {
    thread::spawn(move || { drain_reader(reader, &sink, pid, stream); });
}
fn drain_reader(mut reader: impl Read, sink: &LogSink, pid: u32, stream: &str) {
    let mut buffer = [0; 4096];
    let mut line = Vec::new();
    let mut oversized = false;
    loop {
        let count = match reader.read(&mut buffer) {
            Ok(0) => break, Ok(n) => n,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => break,
        };
        for byte in &buffer[..count] {
            if *byte == b'\n' {
                let text = if oversized { "[oversized console line suppressed]".into() }
                    else { console_line(&String::from_utf8_lossy(&line)) };
                sink.write("INFO", &format!("pid={pid} stream={stream} {text}"));
                line.clear(); oversized = false;
            } else if line.len() < MAX_LINE { line.push(*byte); }
            else { oversized = true; }
        }
    }
    if !line.is_empty() || oversized {
        let text = if oversized { "[oversized console line suppressed]".into() }
            else { console_line(&String::from_utf8_lossy(&line)) };
        sink.write("INFO", &format!("pid={pid} stream={stream} {text}"));
    }
}

pub(crate) fn data_dir_arg(args: &[String]) -> Option<&str> {
    args.iter().enumerate().find_map(|(i, arg)| {
        arg.strip_prefix("--data-dir=").or_else(|| {
            if arg == "--data-dir" { args.get(i + 1).map(String::as_str) } else { None }
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn diagnostics_rotation_is_bounded_and_utf8() {
        let dir = tempfile::tempdir().unwrap();
        let mut file = RollingFile { path: dir.path().join("shell.log"), max_bytes: 80 };
        for _ in 0..30 { file.append("2026-10-04T00:00:00Z [INFO] 启动\n").unwrap(); }
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 3);
        for entry in fs::read_dir(dir.path()).unwrap() {
            let path = entry.unwrap().path();
            assert!(fs::metadata(&path).unwrap().len() <= 80);
            assert!(fs::read_to_string(path).unwrap().contains("启动"));
        }
    }
    #[test]
    fn diagnostics_never_persists_credentials_or_bodies() {
        for line in ["Authorization: Bearer credential-value", "token='credential-value'",
            "ticket=credential-value", "Cookie: credential-value", "{\"token\":\"credential-value\"}",
            "response body: credential-value", "BEARER credential-value"] {
            assert!(!redact(line).contains("credential-value"));
            assert!(!console_line(line).contains("credential-value"));
        }
        for line in ["{", "  \"data\": \"private-payload\"", "private-payload", "}",
            "INFO response: private-payload", "ValueError: private-payload", "    print(private_payload)"] {
            assert!(!console_line(line).contains("private-payload"));
            assert!(!console_line(line).contains("private_payload"));
        }
        assert_eq!(console_line("ValueError: sensitive detail"), "ValueError: [message suppressed]");
        assert!(!redact("x\ny\r\tz").contains('\n'));
    }
    #[test]
    fn diagnostics_failure_throttle_is_per_reason_per_minute() {
        let mut throttle = Throttle::default(); let now = Instant::now();
        assert!(throttle.allow("timeout", now));
        assert!(!throttle.allow("timeout", now + Duration::from_secs(59)));
        assert!(throttle.allow("connection", now));
        assert!(throttle.allow("timeout", now + Duration::from_secs(60)));
    }
    #[test]
    fn diagnostics_blocked_writer_and_full_queue_do_not_block_drain() {
        let (sender, _receiver) = mpsc::sync_channel(1);
        let sink = LogSink { sender };
        let bytes = vec![b'x'; 4 * 1024 * 1024];
        let start = Instant::now();
        drain_reader(io::Cursor::new(bytes), &sink, 1, "stderr");
        for _ in 0..10000 { sink.write("INFO", "queue full"); }
        sink.flush(); // A full queue cannot stall shutdown either.
        assert!(start.elapsed() < Duration::from_secs(5));
        let dir = tempfile::tempdir().unwrap();
        let blocked = dir.path().join("not-a-directory"); fs::write(&blocked, "x").unwrap();
        let mut file = RollingFile { path: blocked.join("shell.log"), max_bytes: 80 };
        assert!(file.append("test\n").is_err());
        let sink = LogSink::new(blocked.join("console.log"));
        drain_reader(io::Cursor::new(b"Traceback (most recent call last):\n"), &sink, 1, "stderr");
    }

    #[test]
    fn diagnostics_disk_contains_only_sanitized_console_and_selected_args() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("core-console.log");
        let sink = LogSink::new(path.clone());
        drain_reader(io::Cursor::new(b"Authorization: Bearer fixture-secret\ntoken=fixture-secret\nticket=fixture-secret\nCookie: fixture-secret\n{\n\"data\":\"fixture-secret\"\n}\nresponse body:\nfixture-secret\nTraceback (most recent call last):\n  File \"main.py\", line 2, in main\nValueError: fixture-secret\n"), &sink, 23, "stderr");
        sink.write("INFO", "finished");
        sink.flush();
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            let text = fs::read_to_string(&path).unwrap_or_default();
            if text.contains("finished") {
                assert!(!text.contains("fixture-secret"));
                assert!(!text.contains("Authorization"));
                assert!(text.contains("Traceback"));
                assert!(text.contains("ValueError: [message suppressed]"));
                assert!(text.contains("File \"main.py\", line 2"));
                assert!(text.lines().all(|line| line.contains("Z [INFO]")));
                break;
            }
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(10));
        }
        let args = vec!["--token".into(), "fixture-secret".into(), "--data-dir=E:/data".into()];
        assert_eq!(data_dir_arg(&args), Some("E:/data"));
    }
}
