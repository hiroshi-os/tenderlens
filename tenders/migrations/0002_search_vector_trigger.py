from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION tenders_tender_search_vector_trigger() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.category, '')), 'C');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tenders_tender_search_vector ON tenders_tender;
CREATE TRIGGER tenders_tender_search_vector
BEFORE INSERT OR UPDATE OF title, description, category
ON tenders_tender
FOR EACH ROW
EXECUTE FUNCTION tenders_tender_search_vector_trigger();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS tenders_tender_search_vector ON tenders_tender;
DROP FUNCTION IF EXISTS tenders_tender_search_vector_trigger();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
    ]
