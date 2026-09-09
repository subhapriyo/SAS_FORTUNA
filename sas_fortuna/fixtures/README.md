# fixtures/

Populated by:

    bench --site <site> export-fixtures --app sas_fortuna

Do not hand-edit the generated JSON here except to remove records that
shouldn't have been exported (see README > Fixture Management). Always
review `git diff` on this folder before committing — an export can pull
in more than you expect if `hooks.py > fixtures` filters are too broad.
