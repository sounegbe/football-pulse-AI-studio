ALTER TABLE drafts ADD COLUMN depth INTEGER NOT NULL DEFAULT 3 CHECK (depth BETWEEN 1 AND 3);
ALTER TABLE drafts ADD COLUMN audio_cues INTEGER NOT NULL DEFAULT 1 CHECK (audio_cues IN (0,1));
ALTER TABLE drafts ADD COLUMN content_mode TEXT NOT NULL DEFAULT 'unknown' CHECK (content_mode IN ('unknown','stub','manual'));
ALTER TABLE revisions ADD COLUMN depth INTEGER NOT NULL DEFAULT 3 CHECK (depth BETWEEN 1 AND 3);
ALTER TABLE revisions ADD COLUMN audio_cues INTEGER NOT NULL DEFAULT 1 CHECK (audio_cues IN (0,1));
ALTER TABLE revisions ADD COLUMN content_mode TEXT NOT NULL DEFAULT 'unknown' CHECK (content_mode IN ('unknown','stub','manual'));
