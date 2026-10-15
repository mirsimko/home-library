CREATE VIRTUAL TABLE books_fts USING fts5(title, sort_key, author, series, isbn, tokenize='trigram');
INSERT INTO books_fts (rowid, title, sort_key, author, series, isbn)
    SELECT id, title, sort_key, author, series, isbn FROM books;
CREATE TRIGGER books_fts_insert AFTER INSERT ON books BEGIN
    INSERT INTO books_fts (rowid, title, sort_key, author, series, isbn)
        VALUES (new.id, new.title, new.sort_key, new.author, new.series, new.isbn);
END;
