//! Agent skills embedded in the MCP server.
//!
//! Each skill is a `SKILL.md` file under `skills/<name>/` with `name` and
//! `description` frontmatter, so the same files can also be copied into any
//! skills-aware agent. They are compiled into the binary and exposed over MCP
//! as resources, prompts and tools.

pub struct Skill {
    pub name: &'static str,
    pub description: &'static str,
    pub body: &'static str,
}

const SOURCES: &[&str] = &[
    include_str!("../skills/dblentry-navigator/SKILL.md"),
    include_str!("../skills/dblentry-record-transactions/SKILL.md"),
    include_str!("../skills/dblentry-reporting/SKILL.md"),
    include_str!("../skills/dblentry-accruals-and-schedules/SKILL.md"),
    include_str!("../skills/dblentry-multi-currency-and-units/SKILL.md"),
];

pub const URI_PREFIX: &str = "dblentry://skills/";

/// Split `---` frontmatter from the markdown body.
fn parse(source: &'static str) -> Skill {
    let rest = source
        .strip_prefix("---")
        .expect("skill is missing frontmatter");
    let (front, body) = rest
        .split_once("\n---")
        .expect("skill frontmatter is not terminated");
    let field = |key: &str| -> &'static str {
        front
            .lines()
            .find_map(|l| l.trim().strip_prefix(key).and_then(|v| v.strip_prefix(':')))
            .map(str::trim)
            .unwrap_or_else(|| panic!("skill frontmatter is missing '{}'", key))
    };
    Skill {
        name: field("name"),
        description: field("description"),
        body: body.trim_start_matches(['\r', '\n']),
    }
}

pub fn all() -> Vec<Skill> {
    SOURCES.iter().map(|s| parse(s)).collect()
}

pub fn find(name: &str) -> Option<Skill> {
    all().into_iter().find(|s| s.name == name)
}

pub fn uri(name: &str) -> String {
    format!("{}{}", URI_PREFIX, name)
}

pub fn name_from_uri(uri: &str) -> Option<&str> {
    uri.strip_prefix(URI_PREFIX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_skill_parses_with_unique_name_and_content() {
        let skills = all();
        assert_eq!(skills.len(), SOURCES.len());
        let mut names: Vec<_> = skills.iter().map(|s| s.name).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), skills.len());
        for s in &skills {
            assert!(!s.description.is_empty(), "{} has no description", s.name);
            assert!(s.body.starts_with('#'), "{} body should start at the heading", s.name);
        }
    }

    #[test]
    fn lookup_by_name_and_uri() {
        let skill = find("dblentry-navigator").expect("navigator skill");
        assert_eq!(name_from_uri(&uri(skill.name)), Some("dblentry-navigator"));
        assert!(find("nope").is_none());
        assert!(name_from_uri("file:///x").is_none());
    }
}
