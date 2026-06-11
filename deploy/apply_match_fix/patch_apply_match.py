from pathlib import Path
import re

path = Path(__file__).with_name("library.deploy.py")
text = path.read_text(encoding="utf-8")

helper = '''async def _merge_duplicate_bib_entry(db: AsyncSession, winner: BibEntry, loser: BibEntry) -> list[str]:
    if not winner.doi and loser.doi:
        winner.doi = loser.doi
    if not winner.journal and loser.journal:
        winner.journal = loser.journal
    if not winner.abstract and loser.abstract:
        winner.abstract = loser.abstract
    if not winner.year and loser.year:
        winner.year = loser.year
    if not winner.volume and loser.volume:
        winner.volume = loser.volume
    if not winner.issue and loser.issue:
        winner.issue = loser.issue
    if not winner.pages and loser.pages:
        winner.pages = loser.pages
    if not winner.venue_type and loser.venue_type:
        winner.venue_type = loser.venue_type
    if not winner.citation_count and loser.citation_count:
        winner.citation_count = loser.citation_count

    winner_authors = json.loads(winner.authors_json) if winner.authors_json else []
    loser_authors = json.loads(loser.authors_json) if loser.authors_json else []
    if not winner_authors and loser_authors:
        winner.authors_json = json.dumps(loser_authors, ensure_ascii=False)

    winner_kw = json.loads(winner.keywords_json) if winner.keywords_json else []
    loser_kw = json.loads(loser.keywords_json) if loser.keywords_json else []
    if not winner_kw and loser_kw:
        winner.keywords_json = json.dumps(loser_kw, ensure_ascii=False)

    if not winner.source_file_id and loser.source_file_id:
        winner.source_file_id = loser.source_file_id

    better_status = {"read": 4, "reading": 3, "has_pdf": 2, "none": 1}
    if better_status.get(loser.reading_status, 0) > better_status.get(winner.reading_status, 0):
        winner.reading_status = loser.reading_status

    link_rows = (
        await db.execute(
            select(BibFilterLink).where(BibFilterLink.bib_entry_id == loser.id)
        )
    ).scalars().all()
    for link in link_rows:
        existing = (
            await db.execute(
                select(BibFilterLink).where(
                    BibFilterLink.bib_entry_id == winner.id,
                    BibFilterLink.filter_job_id == link.filter_job_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            link.bib_entry_id = winner.id
        else:
            await db.delete(link)

    jbe_rows = (
        await db.execute(
            select(JobBibEntry).where(JobBibEntry.bib_entry_id == loser.id)
        )
    ).scalars().all()
    for jbe in jbe_rows:
        existing_jbe = (
            await db.execute(
                select(JobBibEntry).where(
                    JobBibEntry.job_id == jbe.job_id,
                    JobBibEntry.bib_entry_id == winner.id,
                    JobBibEntry.role == jbe.role,
                )
            )
        ).scalar_one_or_none()
        if existing_jbe is None:
            jbe.bib_entry_id = winner.id
        else:
            await db.delete(jbe)

    ri_rows = (
        await db.execute(
            select(ReadingItem).where(
                ReadingItem.bib_entry_id == loser.id,
                ReadingItem.owner_user_id == winner.owner_user_id,
            )
        )
    ).scalars().all()
    for ri in ri_rows:
        ri.bib_entry_id = winner.id

    await db.delete(loser)
    return ["merged_with_local"]


'''

marker = 'class ApplyMatchRequest(BaseModel):\n    candidate: dict\n\n\n'
if marker not in text:
    raise SystemExit("ApplyMatchRequest marker not found")
text = text.replace(marker, marker + helper, 1)

text, count = re.subn(
    r'(?s)        winner, loser = entry, other_entry\n\n        if not winner\.doi and loser\.doi:.*?        updated_fields = \["merged_with_local"\]',
    '        updated_fields = await _merge_duplicate_bib_entry(db, entry, other_entry)',
    text,
    count=1,
)
if count != 1:
    raise SystemExit("local merge block replacement failed")

old = '''    entry.dedup_key = compute_dedup_key(
        normalize_doi(new_doi) or new_doi,
        new_title,
        new_authors,
        new_year,
    )
'''
new = '''    new_dedup_key = compute_dedup_key(
        normalize_doi(new_doi) or new_doi,
        new_title,
        new_authors,
        new_year,
    )
    duplicate_entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user.id,
                BibEntry.id != entry.id,
                BibEntry.dedup_key == new_dedup_key,
            )
        )
    ).scalar_one_or_none()
    if duplicate_entry is not None:
        updated_fields = await _merge_duplicate_bib_entry(db, entry, duplicate_entry)
        await db.flush()
    entry.dedup_key = new_dedup_key
'''
if old not in text:
    raise SystemExit("dedup block not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
