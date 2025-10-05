CREATE TABLE Album (
    ArtistId TEXT,
    Name TEXT,
    TotalSales TEXT,
    a TEXT,
    al TEXT,
    il TEXT,
    t TEXT
);;

CREATE TABLE InvoiceLine (
    ArtistId TEXT,
    Name TEXT,
    TotalSales TEXT,
    a TEXT,
    al TEXT,
    il TEXT,
    t TEXT
);;

CREATE TABLE Track (
    ArtistId TEXT,
    Name TEXT,
    TotalSales TEXT,
    a TEXT,
    al TEXT,
    il TEXT,
    t TEXT
);;

CREATE TABLE VECTOR_SEARCH (
    content TEXT,
    distance TEXT,
    id TEXT,
    question TEXT,
    training_data_type TEXT
);;

CREATE TABLE langchain_pg_embedding (
    cmetadata TEXT,
    document TEXT
);;

CREATE TABLE oracle_collection (
    cmetadata TEXT,
    name TEXT
);;

CREATE TABLE oracle_embedding (
    collection_id TEXT,
    document TEXT
);