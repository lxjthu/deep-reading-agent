"""Source-owned checks. Normalized matches never silently become verbatim matches."""
import re


def locate_quote(quote,documents):
    if not quote: return []
    locations=[]
    compact=''.join(c for c in quote if not c.isspace())
    for doc in documents:
        for page in doc.get('pages',[]):
            text=page['text']; start=text.find(quote)
            if start>=0:
                end=start+len(quote); match='exact'
            else:
                positions=[i for i,c in enumerate(text) if not c.isspace()]
                normalized=''.join(text[i] for i in positions); index=normalized.find(compact) if compact else -1
                if index<0: continue
                start=positions[index]; end=positions[index+len(compact)-1]+1; match='whitespace_only'
            location = {'entry_id':doc['entry_id'],'page_number':page.get('page'),'char_start':start,'char_end':end,'file_sha256':doc.get('file_sha256'),'match':match,'source_quote':text[start:end]}
            if doc.get('citation_basis') or doc.get('source_kind') == 'cleaned_markdown':
                global_start = page.get('start', 0) + start; global_end = page.get('start', 0) + end
                original = [dict(r) for m in doc.get('source_map', []) if m['clean_start'] < global_end and m['clean_end'] > global_start for r in m.get('source_ranges', [])]
                location.update(citation_basis='selected_markdown_not_pdf_verbatim', pdf_verbatim=False, source_version_id=doc.get('source_version_id'),
                    source_ranges=[{'source_file': doc.get('source_markdown'), 'source_version_id': doc.get('source_version_id'), 'start': global_start, 'end': global_end, 'match_method': match}] + original, original_source_ranges=original)
            locations.append(location)
    return locations


def translation_checks(source,translation):
    values=lambda s:set(re.findall(r'(?<![A-Za-z0-9])\d+(?:[,.]\d+)*(?:%|％)?',s))
    numbers=values(source); output=values(translation)
    english=[p for p in translation.split('\n\n') if len(p)>100 and sum(c.isascii() and c.isalpha() for c in p)/max(1,len(p))>.65]
    return {'source_chars':len(source),'output_chars':len(translation),'source_numbers_missing_as_literal':sorted(numbers-output),'output_numbers_not_literal_in_source':sorted(output-numbers),'english_blocks_to_review':len(english),'status':'heuristic_review_only','caution':'Numbers may be legitimately reformatted or translated. Counts cannot prove translation completeness.'}
