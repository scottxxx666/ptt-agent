# Known limitations (accepted)

Behaviours we reviewed and chose not to fix. Add an entry when a review finding is accepted, with the reason, so it is not re-raised.

- Append (`ptt_edit.append_post`) counts lines from the reader's text. If the reader wraps a long body line, its count no longer matches the editor's and the append is abandoned before typing (logged, notified, retried each run, so a Weverse day post with such a line gets no more lives until fixed by hand). Our own posts have short lines; not worth an editor-side search.
