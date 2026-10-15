CREATE TRIGGER books_fts_update AFTER UPDATE ON books BEGIN
    DELETE FROM books_fts WHERE rowid = old.id;
    INSERT INTO books_fts (rowid, title, sort_key, author, series, isbn)
        VALUES (new.id, new.title, new.sort_key, new.author, new.series, new.isbn);
END;
CREATE TRIGGER books_fts_delete AFTER DELETE ON books BEGIN
    DELETE FROM books_fts WHERE rowid = old.id;
END;
