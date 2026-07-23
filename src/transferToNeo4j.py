from os import getenv
from dotenv import load_dotenv
from neo4j import GraphDatabase, ManagedTransaction, Driver
from arango import ArangoClient, database

W7 = ["WHO", "WHAT", "WHERE", "WHICH", "WHEN", "WHY", "HOW"]

def create_notices(arangodb, notice_collection_name, neo4jDriver):
    """
    From a notice document collection, creates a Notice, and the associated Sources according to the schema in `documentation/schema.mmd
    """

    if arangodb.has_collection(notice_collection_name):
        document_collection: database.StandardCollection = arangodb.collection(notice_collection_name)
        document_list = list(document_collection.all())

        with neo4jDriver.session() as session:
            session.execute_write(create_notices_tx, document_list)

def create_notices_tx(tx, documents):
    """
    :param tx:
    :param documents:
    :return:
    """
    noticeQuery = "CREATE (a:Notice {id : $id, name : $name})"
    sourceQuery = "CREATE (a:Source {description : $desc, value : $val)"
    for document in documents:
        tx.run(noticeQuery, id = document["_id"], name = "notice")
        """for key in document:
            for key in document."""

def create_questions(driver : Driver):
    """
    Create the seven W7 questions in the database
    :return:
    """
    with driver.session() as session:
        session.execute_write(create_questions_tx)

def create_questions_tx(tx : ManagedTransaction):
    query = "CREATE (a:Question {name: $name})"

    for W in W7:
        result = tx.run(query,name = W)
        result.single()

def create_concepts(arangodb, thesaurus_name, neo4jDriver):
    """
    Transfers all concepts of a given thesaurus from arangoDB to the instance Neo4j
    :return:
    """

    if arangodb.has_collection(thesaurus_name):
        theso_collection: database.StandardCollection = arangodb.collection(thesaurus_name)
        theso_relations: database.StandardCollection = arangodb.collection(f"{thesaurus_name}_relations")
        concepts_list = list(theso_collection.all())
        relations_list = list(theso_relations.all())

        with neo4jDriver.session() as session:
            session.execute_write(create_concepts_nodes_tx, concepts_list)
            session.execute_write(create_concepts_relations_tx, relations_list)


def create_concepts_nodes_tx(tx, concepts):
    """
    We admit that the concepts are in the expected format
    :param tx:r
    :param concepts:
    :return:
    """

    query = "CREATE (a:Concept {name : $name, id: $id, ark : $ark, description: $desc, note : $note, definition : $definition, thesaurus : $thesaurus})"
    required_keys = ["name", "_id", "ark", "description", "note", "definition"]
    for concept in concepts:
        if not all(key in concept for key in required_keys):
            continue  # The concept is degenerate and needs to be ignored
        result = tx.run(query, name=concept["name"], id = concept["_id"], ark = concept["ark"], desc = concept["description"], note = concept["note"], definition = concept["definition"], thesaurus = concept["_id"].split("/")[0])
        result.single()

def create_concepts_relations_tx(tx, relations):
    query = "MATCH (a:Concept {id : $id1}), (b:Concept {id : $id2}) CREATE (a)-[c:$($rel_label)]->(b)"
    for relation in relations:
        result = tx.run(query, id1 = relation["_from"], id2 = relation["_to"], rel_label = relation["type"])
        result.single()

if __name__ == "__main__":
    load_dotenv()

    #Arango Clients
    arangoclient: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    arangodb: database.StandardDatabase = arangoclient.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                              password=getenv("DB_PASSWORD"))

    curr_driver : Driver = GraphDatabase.driver(getenv("NEO4J_URL"), auth=(getenv("NEO4J_USER"), getenv("NEO4J_PASSWORD")))

    thesaurus_collections = []
    create_questions(curr_driver)

    for collection in arangodb.collections():
        if collection["name"].find("th") == 0 and collection["name"].find("_relations") == -1:  # It is a thesaurus
            thesaurus_collections.append(collection["name"])

    for coll in thesaurus_collections:
        create_concepts(arangodb, coll, curr_driver)