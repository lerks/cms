CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS '
BEGIN
    IF TG_OP = ''INSERT'' THEN
        PERFORM pg_notify (''create'', TG_RELNAME || '' '' || CAST(NEW.id AS text));
    END IF;
    IF TG_OP = ''UPDATE'' THEN
        IF OLD.id IS DISTINCT FROM NEW.id THEN
            PERFORM pg_notify (''rename'', TG_RELNAME || '' '' || CAST(OLD.id AS text) || '' '' || CAST(NEW.id AS text));
        END IF;
        PERFORM pg_notify (''update'', TG_RELNAME || '' '' || CAST(NEW.id AS text));
    END IF;
    IF TG_OP = ''DELETE'' THEN
        PERFORM pg_notify (''delete'', TG_RELNAME || '' '' || CAST(OLD.id AS text));
    END IF;
    RETURN NULL;
END
' LANGUAGE plpgsql;

-- If we could generate these queries automatically life would be much simpler

CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON contests
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON announcements
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();

CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON tasks
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON statements
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON attachments
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON task_testcases
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON managers
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON submission_format_elements
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();

CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON messages
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON questions
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();

CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON submissions
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON tokens
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON files
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON executables
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON evaluations
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();

CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON user_tests
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON user_test_files
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON user_test_executables
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
CREATE TRIGGER watcher AFTER INSERT OR UPDATE OR DELETE ON user_test_managers
    FOR EACH ROW EXECUTE PROCEDURE notify_change ();
