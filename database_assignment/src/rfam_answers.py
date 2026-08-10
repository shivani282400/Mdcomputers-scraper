"""
rfam_answers.py

Answers three questions using the public Rfam database:
  a) How many distinct Acacia species appear in the taxonomy table?
  b) Which Triticum (wheat) sequence has the longest DNA sequence length?
  c) Page 9 (15 results/page) of families with longest sequence length
     greater than 1,000,000, ordered by length descending.

Schema reference: https://docs.rfam.org/en/latest/database.html
"""

import pymysql

DB_CONFIG = {
    "host": "mysql-rfam-public.ebi.ac.uk",
    "port": 4497,
    "user": "rfamro",
    "password": "",
    "database": "Rfam",
}


def get_connection():
    """Open and return a new connection to the Rfam public database."""
    return pymysql.connect(**DB_CONFIG)


def count_species_by_genus(cursor, genus: str) -> int:
    """Return the number of distinct species belonging to `genus`."""
    cursor.execute(
        "SELECT COUNT(DISTINCT species) FROM taxonomy WHERE species LIKE %s",
        (f"{genus}%",),
    )
    return cursor.fetchone()[0]


def longest_sequence_by_genus(cursor, genus: str):
    """Return (species, rfamseq_acc, length) for the longest sequence in `genus`."""
    cursor.execute(
        """
        SELECT tx.species, rs.rfamseq_acc, rs.length
        FROM rfamseq rs
        JOIN taxonomy tx ON rs.ncbi_id = tx.ncbi_id
        WHERE tx.species LIKE %s
        ORDER BY rs.length DESC
        LIMIT 1
        """,
        (f"{genus}%",),
    )
    return cursor.fetchone()


def paginated_families_by_max_length(cursor, min_length: int, page_number: int, page_size: int):
    """
    Return a page of (rfam_acc, rfam_id, max_length) for families whose
    longest matched sequence exceeds `min_length`, ordered by length
    descending. Pagination offset = (page_number - 1) * page_size.
    """
    offset = (page_number - 1) * page_size
    cursor.execute(
        """
        SELECT f.rfam_acc, f.rfam_id, MAX(rs.length) AS max_length
        FROM family f
        JOIN full_region fr ON f.rfam_acc = fr.rfam_acc AND fr.is_significant = 1
        JOIN rfamseq rs ON fr.rfamseq_acc = rs.rfamseq_acc
        GROUP BY f.rfam_acc, f.rfam_id
        HAVING MAX(rs.length) > %s
        ORDER BY max_length DESC
        LIMIT %s OFFSET %s
        """,
        (min_length, page_size, offset),
    )
    return cursor.fetchall()


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # a) Acacia species count
            genus_a = "Acacia"
            count = count_species_by_genus(cursor, genus_a)
            print(f"a) Distinct {genus_a} species: {count}")

            # b) Longest wheat sequence
            genus_b = "Triticum"
            longest = longest_sequence_by_genus(cursor, genus_b)
            print(f"\nb) Longest {genus_b} sequence:")
            print(f"   species={longest[0]}, accession={longest[1]}, length={longest[2]}")

            # c) Paginated families
            page_number, page_size, min_length = 9, 15, 1_000_000
            rows = paginated_families_by_max_length(cursor, min_length, page_number, page_size)
            print(f"\nc) Page {page_number} ({page_size}/page, length > {min_length:,}):")
            if not rows:
                print("   No results on this page.")
            for row in rows:
                print(f"   rfam_acc={row[0]}, rfam_id={row[1]}, max_length={row[2]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
