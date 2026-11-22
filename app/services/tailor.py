"""Resume tailoring with a hard safety rule.

The blueprint's safety requirement: a tailored resume must never add
unsupported skills, employers, qualifications or achievements. That rule is
enforced in code, not just in a prompt: validate_draft() checks every skill
and employer in the output against the parsed profile, and the API refuses
to save a draft that invents anything. Claude (when configured) only
rephrases and reorders facts that are already there.
"""
from typing import List, Optional, Tuple

from ..schemas import ChangeEntry, ProfileData
from .llm import llm


def _matched_skills(profile: ProfileData, job_skills: List[str]) -> List[str]:
    job_set = {s.lower() for s in job_skills}
    return [s for s in profile.skills if s.lower() in job_set]


def tailor(profile: ProfileData, job) -> Tuple[dict, List[ChangeEntry], str]:
    """Build a role-specific draft from the profile. `job` is the ORM Job.

    Deterministic construction: matched skills first, a summary that names
    the target role, and experience entries reordered by relevance. Every
    difference from the original profile is logged as a ChangeEntry with its
    source, so the user reviews edits rather than trusting them.
    """
    changes: List[ChangeEntry] = []
    job_skills = job.skills_list()
    matched = _matched_skills(profile, job_skills)
    rest = [s for s in profile.skills if s not in matched]
    ordered_skills = matched + rest

    if matched != profile.skills[:len(matched)]:
        changes.append(ChangeEntry(
            section="skills",
            change="reorder",
            before=", ".join(profile.skills[:8]),
            after=", ".join(ordered_skills[:8]),
            source=f"Job requires: {', '.join(job_skills)}",
        ))

    years = sum(e.years for e in profile.experience)
    summary = (f"{profile.name or 'Candidate'} targeting the {job.title} role at "
               f"{job.company}. "
               + (f"Brings {years:.1f} years of experience. " if years else "")
               + (f"Relevant skills include {', '.join(matched[:5])}."
                  if matched else "Profile matches the role's general direction."))
    changes.append(ChangeEntry(
        section="summary",
        change="summary",
        before="(no tailored summary)",
        after=summary,
        source=f"Target role: {job.title} at {job.company}",
    ))

    # Reorder experience by skill overlap with the job; content is unchanged.
    def relevance(entry) -> int:
        blob = (entry.title + " " + entry.company).lower()
        return sum(1 for s in job_skills if s.lower() in blob)

    original_experience = list(profile.experience)
    ordered_experience = sorted(original_experience, key=relevance, reverse=True)
    if [e.model_dump() for e in ordered_experience] != [e.model_dump() for e in original_experience]:
        changes.append(ChangeEntry(
            section="experience",
            change="reorder",
            before="; ".join(e.title for e in original_experience),
            after="; ".join(e.title for e in ordered_experience),
            source="Entries mentioning job-relevant skills are shown first.",
        ))

    for skill in matched:
        changes.append(ChangeEntry(
            section="skills",
            change="emphasize",
            before=skill,
            after=f"{skill} (matched to job requirement)",
            source=f"Listed in candidate profile and required by {job.title}.",
        ))

    draft = {
        "name": profile.name,
        "target_role": f"{job.title} - {job.company}",
        "summary": summary,
        "skills": ordered_skills,
        "experience": [e.model_dump() for e in ordered_experience],
        "education": [e.model_dump() for e in profile.education],
    }
    return draft, changes, llm.mode


def validate_draft(draft: dict, profile: ProfileData) -> List[str]:
    """Safety check: the draft may not invent anything. Returns violations."""
    violations: List[str] = []
    profile_skills = {s.lower() for s in profile.skills}
    for skill in draft.get("skills", []):
        if skill.lower() not in profile_skills:
            violations.append(f"Draft adds skill not in profile: {skill}")
    profile_companies = {e.company.lower() for e in profile.experience}
    for entry in draft.get("experience", []):
        if entry.get("company", "").lower() not in profile_companies:
            violations.append(f"Draft adds employer not in profile: {entry.get('company')}")
    profile_degrees = {e.degree.lower() for e in profile.education}
    for entry in draft.get("education", []):
        if entry.get("degree", "").lower() not in profile_degrees:
            violations.append(f"Draft adds qualification not in profile: {entry.get('degree')}")
    return violations
