from os import getenv
from arango import ArangoClient, database
from dotenv import load_dotenv

import spacy
from spacy.matcher import PhraseMatcher

spacy.prefer_gpu()

def link_document_coll_with_thesaurus(db: database.StandardDatabase, thesaurus_name : str, document_collection_name : str, nlp : spacy.Language):
    """
    From a thesaurus name and collection name, search all links through word tokenization between a document and the concept names of a thesaurus.
    :param db: ArangoDB database API wrapper
    :param thesaurus_name:
    :param document_collection_name:
    :param nlp: Spacy language model instance.
    :return:
    """
    edge_collection_name = f"{document_collection_name}_linking"

    if not db.has_collection(thesaurus_name):
        print(f"The {thesaurus_name} collection is not in the database")

    if not db.has_collection(document_collection_name):
        print(f"The {document_collection_name} collection is not in the database")

    thesaurus_coll = db.collection(thesaurus_name)
    document_collection : database.StandardCollection = db.collection(document_collection_name)

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

def link_all_notices() -> None:
    """
    Manages linking all notice collections defined in the .env, to all the available thesaurus in the database.
    Results are stored in the associated linking collection in the database itself.
    """

    load_dotenv()
    client: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    db: database.StandardDatabase = client.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                              password=getenv("DB_PASSWORD"))

    notice_collections = getenv("DOC_COLLECTIONS").split(",")

    for coll in notice_collections:
        edge_coll = f"{coll}_linking"
        if db.has_collection(edge_coll):
            db.collection(edge_coll).truncate()

    thesaurus_collections = []

    for collection in db.collections():
        if collection["name"].find("th") == 0 and collection["name"].find("_relations") == -1:  # It is a thesaurus
            thesaurus_collections.append(collection["name"])

    french_nlp = spacy.load("fr_dep_news_trf")

    for document_collection in notice_collections:
        for theso_collection in thesaurus_collections:
            link_document_coll_with_thesaurus(db, theso_collection, document_collection, french_nlp)