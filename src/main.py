from os import getenv
from arango import ArangoClient, database
from dotenv import load_dotenv
import spacy
from spacy.matcher import PhraseMatcher

spacy.prefer_gpu()

def link_document_coll_with_thesaurus(thesaurus_name, document_collection_name):
    edge_collection_name = f"{document_collection_name}_linking"
    graph_name = f"{document_collection_name}_to_{thesaurus_name}"
    load_dotenv()
    client: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    db: database.StandardDatabase = client.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                              password=getenv("DB_PASSWORD"))

    if not db.has_collection(thesaurus_name):
        print(f"The {thesaurus_name} collection is not in the database")

    if not db.has_collection(document_collection_name):
        print(f"The {document_collection_name} collection is not in the database")

    thesaurus_coll = db.collection(thesaurus_name)
    document_collection = db.collection(document_collection_name)

    if db.has_collection(edge_collection_name):
        edge_collection: database.StandardCollection = db.collection(edge_collection_name)
    else:
        edge_collection: database.StandardCollection = db.create_collection(edge_collection_name, edge=True)

    nlp = spacy.load("fr_dep_news_trf")
    matcher = PhraseMatcher(nlp.vocab)

    name_to_id_thesaurus_map = {}
    for term in thesaurus_coll.all():
        name_to_id_thesaurus_map[term['name']] = term['_id']

    thesaurus_terms_patterns = [nlp(term['name']) for term in thesaurus_coll.all()]
    matcher.add(thesaurus_name, thesaurus_terms_patterns)

    for document in document_collection.all():
        for question in document:
            if question in ["HOW", "WHERE", "WHEN", "WHO", "WHY", "WHICH", "WHAT"]:
                for source in document[question]:
                    if document[question][source]["value"] is not None and document[question][source]["value"] != "":
                        text = nlp(document[question][source]["value"])
                        matches = matcher(text)
                        for match_id, start, end in matches:
                            span = text[start:end]
                            edge_collection.insert(
                                {"_from": document["_id"], "_to": name_to_id_thesaurus_map[span.text], "question": question,
                                 "source": source}
                            )

    if db.has_graph(graph_name):
        db.delete_graph(graph_name)

    curr_graph = db.create_graph(graph_name)

    curr_graph.create_edge_definition(
        edge_collection=edge_collection_name,
        from_vertex_collections=[document_collection_name],
        to_vertex_collections=[thesaurus_name]
    )

if __name__ == "__main__":
    load_dotenv()
    client: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    db: database.StandardDatabase = client.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                              password=getenv("DB_PASSWORD"))

    for document_collection in ["palissy","merimee","joconde"]:
        for collection in db.collections():
            if collection["name"].find("th") == 0 and collection["name"].find("_relations") == -1: #It is a thesaurus
                link_document_coll_with_thesaurus(collection["name"], document_collection)
