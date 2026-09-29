use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Write};
use std::path::Path;

use anyhow::{Context, Result};
use ratatui::style::Color;
use serde::Serialize;

use crate::adapters::adapter_for;
use crate::config::AGENTS;
use crate::model::{Session, YoloPolicy};

pub const DEFAULT_LIST_LIMIT: usize = 50;
pub const LIST_SCHEMA_VERSION: u32 = 1;
pub const PICK_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Serialize)]
struct SessionOutput<'a> {
    id: &'a str,
    agent: &'a str,
    title: &'a str,
    name: Option<&'a str>,
    directory: &'a str,
    timestamp: &'a chrono::DateTime<chrono::Local>,
    message_count: usize,
    resume_command: Vec<String>,
}

impl<'a> SessionOutput<'a> {
    /// Post: `resume_command` carries yolo flags only when `yolo` decides for
    /// them; with no prompt to ask, an undecided session resumes without.
    fn new(session: &'a Session, yolo: YoloPolicy) -> Self {
        let yolo = yolo.decide(session).unwrap_or(false);
        let resume_command = adapter_for(&session.agent)
            .map(|adapter| adapter.resume_command(session, yolo))
            .unwrap_or_default();
        Self::with_command(session, resume_command)
    }

    fn with_command(session: &'a Session, resume_command: Vec<String>) -> Self {
        Self {
            id: &session.id,
            agent: &session.agent,
            title: &session.title,
            name: (!session.name.is_empty()).then_some(session.name.as_str()),
            directory: &session.directory,
            timestamp: &session.timestamp,
            message_count: session.message_count,
            resume_command,
        }
    }
}

#[derive(Debug, Serialize)]
struct PaginationMeta {
    state: PaginationState,
    total: usize,
    offset: usize,
    limit: usize,
    returned: usize,
    next_offset: Option<usize>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
enum PaginationState {
    More,
    Complete,
    PastEnd,
}

#[derive(Debug, Serialize)]
struct SessionListOutput<'a> {
    schema_version: u32,
    sessions: Vec<SessionOutput<'a>>,
    meta: PaginationMeta,
    agents: BTreeMap<&'static str, AgentStyleOutput>,
}

/// How the TUI draws an agent, for consumers that draw sessions themselves.
#[derive(Debug, Serialize)]
struct AgentStyleOutput {
    badge: &'static str,
    color: Option<[u8; 3]>,
    light_color: Option<[u8; 3]>,
}

/// Every agent `fr` knows, keyed as a session's `agent`, with the badge and the
/// dark- and light-theme colors the TUI draws it in.
/// Post: one entry per `config::AGENT_ORDER` key.
fn agent_palette() -> BTreeMap<&'static str, AgentStyleOutput> {
    AGENTS
        .iter()
        .map(|(&key, agent)| {
            let style = AgentStyleOutput {
                badge: agent.badge,
                color: rgb(agent.color),
                light_color: rgb(agent.light_color),
            };
            (key, style)
        })
        .collect()
}

/// `[r, g, b]` for an RGB color; `None` for one the terminal defines.
fn rgb(color: Color) -> Option<[u8; 3]> {
    match color {
        Color::Rgb(r, g, b) => Some([r, g, b]),
        _ => None,
    }
}

#[derive(Debug, Serialize)]
struct PickOutput<'a> {
    schema_version: u32,
    session: Option<SessionOutput<'a>>,
}

/// Write the session a picker chose, or a `null` session when it was
/// cancelled, as one JSON object. `resume_command` is exactly what the picker
/// would have run, so the caller can resume the session itself.
pub fn write_pick_json(path: &Path, picked: Option<(&Session, Vec<String>)>) -> Result<()> {
    let output = PickOutput {
        schema_version: PICK_SCHEMA_VERSION,
        session: picked.map(|(session, command)| SessionOutput::with_command(session, command)),
    };
    fs::write(path, serde_json::to_vec(&output)?)
        .with_context(|| format!("failed to write the picked session to {}", path.display()))
}

pub fn print_sessions_json(
    sessions: &[Session],
    total: usize,
    offset: usize,
    limit: usize,
    yolo: YoloPolicy,
) -> Result<()> {
    let returned = sessions.len();
    let has_more = offset.saturating_add(returned) < total;
    let state = if total > 0 && offset >= total {
        PaginationState::PastEnd
    } else if has_more {
        PaginationState::More
    } else {
        PaginationState::Complete
    };
    let output = SessionListOutput {
        schema_version: LIST_SCHEMA_VERSION,
        sessions: sessions
            .iter()
            .map(|session| SessionOutput::new(session, yolo))
            .collect(),
        meta: PaginationMeta {
            state,
            total,
            offset,
            limit,
            returned,
            next_offset: has_more.then_some(offset.saturating_add(returned)),
        },
        agents: agent_palette(),
    };

    let stdout = io::stdout();
    let mut writer = stdout.lock();
    serde_json::to_writer(&mut writer, &output)?;
    writeln!(writer)?;
    Ok(())
}

pub fn print_sessions_table(sessions: &[Session], total: usize, offset: usize) {
    if sessions.is_empty() {
        println!("No sessions found.");
        return;
    }

    println!("{:<15}  {:<52}  {:<38}  ID", "Agent", "Title", "Directory");
    println!("{}", "-".repeat(124));
    for session in sessions {
        println!(
            "{:<15}  {:<52}  {:<38}  {}",
            session.agent,
            truncate_for_terminal(&session.title, 52),
            truncate_for_terminal(&session.display_directory(), 38),
            session.id
        );
    }

    if offset == 0 {
        println!("\nShowing {} of {} sessions", sessions.len(), total);
    } else {
        println!(
            "\nShowing {}-{} of {} sessions",
            offset + 1,
            offset + sessions.len(),
            total
        );
    }
    let next_offset = offset + sessions.len();
    if next_offset < total {
        eprintln!("More sessions available; continue with --offset {next_offset}");
    }
}

fn truncate_for_terminal(value: &str, width: usize) -> String {
    if value.chars().count() <= width {
        return value.to_string();
    }
    let keep = width.saturating_sub(3);
    let mut out: String = value.chars().take(keep).collect();
    out.push_str("...");
    out
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use chrono::Local;
    use serde_json::json;

    use super::*;
    use crate::config::AGENT_ORDER;

    #[test]
    fn pagination_state_distinguishes_boundaries() {
        let session = Session::new("id", "codex", "Title", "/repo", Local::now(), "content", 1);

        let json = serde_json::to_value(SessionListOutput {
            schema_version: LIST_SCHEMA_VERSION,
            sessions: vec![SessionOutput::new(&session, YoloPolicy::Ask)],
            meta: PaginationMeta {
                state: PaginationState::More,
                total: 2,
                offset: 0,
                limit: 1,
                returned: 1,
                next_offset: Some(1),
            },
            agents: BTreeMap::new(),
        })
        .unwrap();

        assert_eq!(json["schema_version"], 1);
        assert_eq!(json["meta"]["state"], "more");
        assert_eq!(json["meta"]["next_offset"], 1);
        assert!(json["sessions"][0].get("content").is_none());
        assert!(json["sessions"][0].get("mtime").is_none());
        assert!(json["sessions"][0].get("yolo").is_none());
    }

    #[test]
    fn explicit_names_are_reported_and_unnamed_sessions_are_null() {
        let mut named = Session::new("n", "codex", "Named", "/repo", Local::now(), "content", 1);
        named.name = "Named".to_string();
        let unnamed = Session::new("u", "codex", "Prompt", "/repo", Local::now(), "content", 1);

        let json = serde_json::to_value([
            SessionOutput::new(&named, YoloPolicy::Ask),
            SessionOutput::new(&unnamed, YoloPolicy::Ask),
        ])
        .unwrap();

        assert_eq!(json[0]["name"], "Named");
        assert!(json[1]["name"].is_null());
    }

    #[test]
    fn agent_palette_has_an_entry_per_agent() {
        let palette = agent_palette();

        let keys: BTreeSet<&str> = palette.keys().copied().collect();
        assert_eq!(keys, AGENT_ORDER.into_iter().collect::<BTreeSet<_>>());
    }

    #[test]
    fn agent_palette_carries_the_tui_badge_and_rgb_colors() {
        let palette = serde_json::to_value(agent_palette()).unwrap();

        for (key, agent) in AGENTS.iter() {
            let (Color::Rgb(r, g, b), Color::Rgb(lr, lg, lb)) = (agent.color, agent.light_color)
            else {
                panic!("{key} is not styled in RGB");
            };
            assert_eq!(palette[*key]["badge"], agent.badge);
            assert_eq!(palette[*key]["color"], json!([r, g, b]));
            assert_eq!(palette[*key]["light_color"], json!([lr, lg, lb]));
        }
    }

    #[test]
    fn a_color_without_rgb_components_is_reported_as_null() {
        assert_eq!(rgb(Color::Reset), None);
    }
}
