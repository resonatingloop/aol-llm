-- Image snapshots belong to messages and disappear with the owning message/chat.
CREATE TABLE message_images (
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    name TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN (
        'image/png', 'image/jpeg', 'image/gif', 'image/webp'
    )),
    data BLOB NOT NULL,
    PRIMARY KEY (message_id, position)
);
