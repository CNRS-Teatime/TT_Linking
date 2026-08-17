from os import getenv
from dotenv import load_dotenv
from neo4j import GraphDatabase, ManagedTransaction, Driver
from arango import ArangoClient, database

W7 = ["WHO", "WHAT", "WHERE", "WHICH", "WHEN", "WHY", "HOW"]


def create_notices(arangodb, neo4jDriver, notice_collection_name: str) -> None:
    """
    Transaction manager.
    From a notice document collection, creates each Notice, and the associated Sources according to the schema in `documentation/schema.mmd

    :param arangodb: The arangoDB database API wrapper
    :param neo4jDriver: The neo4j driver for the desired databases
    :param notice_collection_name: The notice collection to transfer
    :return:
    """

    if arangodb.has_collection(notice_collection_name):
        document_collection: database.StandardCollection = arangodb.collection(notice_collection_name)
        document_list = list(document_collection.all())

        i = 0

        with neo4jDriver.session() as session:
            for document in document_list:
                i += 1
                print(f"{(i / len(document_list)) * 100}%")
                session.execute_write(create_notice_tx, document)


def create_notice_tx(tx: ManagedTransaction, document: dict[str, dict]) -> None:
    """
    Query manager.
    From a single notice, create the notice node and all associated sources, with the correct links
    :param tx: neo4j transaction manager
    :param document: A single notice as a dictionary
    :return:
    """
    # Create a notice node
    notice_query = "CREATE (a:Notice {id : $id, name : $name})"
    # Create a Justification for a notice and link it to its question
    source_query = ("MATCH (n:Notice {id : $noticeID}), (q:Question {name: $QuestionName}) "
                    "CREATE (n)<-[:hasNotice]-(a:Source {id: randomUUID(),description : $desc, value : $val, key : $key})-[:hasQuestion]->(q) "
                    "RETURN a.id AS sourceID")

    tx.run(notice_query, id=document["_id"], name="notice")
    for current_question_name in document:
        if current_question_name in W7:
            for key in document[current_question_name]:
                if document[current_question_name][key]["value"] is not None and document[current_question_name][key][
                    "value"].replace(" ", "") != "":
                    tx.run(source_query,
                           noticeID=document["_id"],
                           desc=document[current_question_name][key]["description"],
                           val=document[current_question_name][key]["value"],
                           key=key,
                           QuestionName=current_question_name
                           )


def create_questions(driver: Driver) -> None:
    """
    Transaction manager
    Create the seven W7 questions in the database
    :param driver: neo4J driver
    :return:
    """
    with driver.session() as session:
        session.execute_write(create_questions_tx)


def create_questions_tx(tx: ManagedTransaction) -> None:
    """
    Query manager for creating the W7 seven questions
    :param tx: neo4j transaction manager
    :return:
    """
    query = "CREATE (a:Question {name: $name})"

    for W in W7:
        tx.run(query, name=W)


def create_concepts(arangodb : database.StandardDatabase, neo4jDriver : Driver, thesaurus_name: str) -> None:
    """
    Transaction manager for creating the concepts and their relations.
    Transfers all concepts of a given thesaurus from arangoDB to the Neo4j instance
    :param arangodb: The arangoDB database API wrapper
    :param neo4jDriver: The neo4j driver for the desired databases
    :param thesaurus_name: Which thesaurus to transfer
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


def create_concepts_nodes_tx(tx: ManagedTransaction, concepts: list[dict[str, str]]) -> None:
    """
    Query manager for creating the concept nodes.
    The concepts should contain ["name", "_id", "ark", "description", "note", "definition"] otherwise they are ignored.
    :param tx: neo4j transaction manager
    :param concepts: A list of concepts to create. Concepts are dictionaries
    :return:
    """

    query = "CREATE (a:Concept {name : $name, id: $id, ark : $ark, description: $desc, note : $note, definition : $definition, thesaurus : $thesaurus})"
    required_keys = ["name", "_id", "ark", "description", "note", "definition"]
    for concept in concepts:
        if not all(key in concept for key in required_keys):
            continue  # The concept is degenerate and needs to be ignored
        tx.run(query, name=concept["name"], id=concept["_id"], ark=concept["ark"], desc=concept["description"],
               note=concept["note"], definition=concept["definition"], thesaurus=concept["_id"].split("/")[0])


def create_concepts_relations_tx(tx: ManagedTransaction, relations: list[dict[str, str]]) -> None :
    """
    Query manager for relations between concepts
    :param tx: Neo4j transaction wrapper
    :param relations: A list of relations between concepts to create.
    :return:
    """
    query = "MATCH (a:Concept {id : $id1}), (b:Concept {id : $id2}) CREATE (a)-[c:$($rel_label)]->(b)"
    for relation in relations:
        tx.run(query, id1=relation["_from"], id2=relation["_to"], rel_label=relation["type"])


def associate_source_and_concept(arangodb: database.StandardDatabase, neo4jDriver: Driver, notice_collection_name: str) -> None:
    """
    Transaction manager for associating source and concept in neo4J
    :param arangodb: The arangoDB database API wrapper
    :param neo4jDriver: the neo4j driver for the desired database
    :param notice_collection_name: which notice collection to work on
    :return:
    """
    relations_collection_name = f"{notice_collection_name}_linking"
    if arangodb.has_collection(relations_collection_name):
        relations_collection: database.StandardCollection = arangodb.collection(relations_collection_name)
        relations_list = list(relations_collection.all())

        with neo4jDriver.session() as session:
            for relation in relations_list:
                session.execute_write(associate_source_and_concept_tx, relation)


def associate_source_and_concept_tx(tx: ManagedTransaction, relation: dict[str, str]) -> None:
    """
    Query manager for associating source and concepts
    :param tx: Neo4j transaction wrapper
    :param relation: ArangoDB relation to transfer to neo4J
    :return:
    """

    associaton_query = (
        "MATCH (:Notice {id : $noticeID})<-[]-(b:Source {key : $sourceKey}), (c:Concept {id: $conceptID})"
        "CREATE (b)-[:hasConcept]->(c)")

    tx.run(associaton_query, noticeID=relation["_from"], sourceKey=relation["source"], conceptID=relation["_to"])


def transfer_links_to_neo4j() -> None:
    """
    Uses environment variables defined in the `.env` file
    Transfers the DOC_COLLECTIONS and all thesaurus from an arangoDB instance as well as the links between them, following the
    schema found in `documentation/Linking_schema.png`.
    """
    load_dotenv()

    #Arango Clients
    arangoclient: ArangoClient = ArangoClient(hosts=getenv("DB_ADDRESS"))
    arangodb: database.StandardDatabase = arangoclient.db(getenv("DB_NAME"), username=getenv("DB_USER"),
                                                          password=getenv("DB_PASSWORD"))

    curr_driver: Driver = GraphDatabase.driver(getenv("NEO4J_URL"),
                                               auth=(getenv("NEO4J_USER"), getenv("NEO4J_PASSWORD")),
                                               database=getenv("NEO4J_DATABASE"))

    thesaurus_collections = []

    create_questions(curr_driver)

    for collection in arangodb.collections():
        if collection["name"].find("th") == 0 and collection["name"].find("_relations") == -1:  # It is a thesaurus
            thesaurus_collections.append(collection["name"])

    print("Starting concepts")

    for coll_name in thesaurus_collections:
        print(coll_name)
        create_concepts(arangodb, curr_driver, coll_name)

    print("Starting notices")

    for coll_name in ["merimee", "palissy", "joconde"]:
        print(coll_name)
        create_notices(arangodb, curr_driver, coll_name)

    print("Starting source to concepts")

    for coll_name in ["merimee", "palissy", "joconde"]:
        print(coll_name)
        associate_source_and_concept(arangodb, curr_driver, coll_name)
