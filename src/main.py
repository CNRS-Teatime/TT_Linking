from os import getenv
from arango import ArangoClient, database
from dotenv import load_dotenv
import spacy
from spacy.matcher import PhraseMatcher

spacy.prefer_gpu()

def link_document_coll_with_thesaurus(db, thesaurus_name, document_collection_name, nlp : spacy.Language):
    edge_collection_name = f"{document_collection_name}_linking"
    graph_name = f"{document_collection_name}_to_{thesaurus_name}"

    if not db.has_collection(thesaurus_name):
        print(f"The {thesaurus_name} collection is not in the database")

    if not db.has_collection(document_collection_name):
        print(f"The {document_collection_name} collection is not in the database")

    thesaurus_coll = db.collection(thesaurus_name)
    document_collection : StandardCollection = db.collection(document_collection_name)

    if db.has_collection(edge_collection_name):
        edge_collection: database.StandardCollection = db.collection(edge_collection_name)
    else:
        edge_collection: database.StandardCollection = db.create_collection(edge_collection_name, edge=True)

    matcher = PhraseMatcher(nlp.vocab)

    name_to_id_thesaurus_map = {}
    for term in thesaurus_coll.all():
        if term['name'] is not None and term['name'] != "":
            name_to_id_thesaurus_map[term['name']] = term['_id']

    thesaurus_terms_patterns = [nlp(term) for term in name_to_id_thesaurus_map.keys()]
    matcher.add(thesaurus_name, thesaurus_terms_patterns)

    documents = list(document_collection.all())

    for document in documents:
        for question in document:
            if question in ["HOW", "WHERE", "WHEN", "WHO", "WHY", "WHICH", "WHAT"]:
                for source in document[question]:
                    if document[question][source]["value"] is not None and document[question][source]["value"].replace(" ", "") != "":
                        try:
                            text = nlp(document[question][source]["value"])
                            matches = matcher(text)
                            for match_id, start, end in matches:
                                span = text[start:end]
                                edge_collection.insert(
                                    {"_from": document["_id"], "_to": name_to_id_thesaurus_map[span.text],
                                     "question": question,
                                     "source": source}
                                )
                        except:
                            print(f"Error with value : {document[question][source]["value"]}")

if __name__ == "__main__":
    load_dotenv()
    client: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    db: database.StandardDatabase = client.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                              password=getenv("DB_PASSWORD"))

    for coll in ["palissy_linking", "merimee_linking", "joconde_linking"]:
        if db.has_collection(coll):
            db.collection(coll).truncate()

    thesaurus_collections = []

    for collection in db.collections():
        if collection["name"].find("th") == 0 and collection["name"].find("_relations") == -1:  # It is a thesaurus
            thesaurus_collections.append(collection["name"])

    french_nlp = spacy.load("fr_dep_news_trf")

    for document_collection in ["palissy","merimee","joconde"]:
        for theso_collection in thesaurus_collections:
            link_document_coll_with_thesaurus(db, theso_collection, document_collection, french_nlp)
