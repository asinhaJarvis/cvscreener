import os, re, base64, mimetypes, shutil
from io import BytesIO
import json, datetime, logging, tiktoken
import azure.functions as func
from pypdf import PdfReader
from langchain.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI
import openai
import asyncio  # Import asyncio for concurrency
from azure.cosmos import CosmosClient, PartitionKey
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
#from utils import upload_blob_to_azure, extract_text_from_pdf, convert_to_json, createCVs, createJDs, delTempFolder


#--------Setting Environmental Variables and Credentials -----------  
# Get current date to append to filenames
date_str = datetime.datetime.now().strftime('%Y%m%d')
time_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

# Initialize variables
results1 = []
results2 = []
results = []
cv_json_content = {}    # extracted cv information

# Openai details
openai.api_key = "XXXXXXXXXXXXXXXXXXXXXXXXXXx"
openai.api_version = "XXXXXXXXXXX"

# Define llm
llm = AzureChatOpenAI(azure_endpoint="https://abc.openai.azure.com/", api_version=openai.api_version,
                            azure_deployment="Xxxxxxx", api_key=openai.api_key)

# Azure Cosmos DB details
DATABASE_NAME = 'recruitmentdocs'
JD_CONTAINER_NAME = 'JDs'
CV_CONTAINER_NAME = 'CVs'
ENDPOINT = "https://abcd.documents.azure.com:443/"
PRIMARY_KEY = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
CV_UPLOAD_FOLDER = 'data-'+time_str
MAX_CVS = 5
skip_CV = False #Skip CV in case it exceeds allowed token limit

#--------------------------- Defining the modules ----------------------------------------
# Initializing Azure Cosmos DB
def initialize_db():
    URL = ENDPOINT
    KEY = PRIMARY_KEY
    client = CosmosClient(URL, credential=KEY)
    database = client.get_database_client(DATABASE_NAME)   
    container1 = database.get_container_client(JD_CONTAINER_NAME) 
    container2 = database.get_container_client(CV_CONTAINER_NAME)
    return database, container1, container2

dbDetails = initialize_db()
database = dbDetails[0]
jd_container = dbDetails[1]
cv_container = dbDetails[2]
    
# Creating JD entries in CosmosDb
def createJDs(jdinfo):   
    try:
        # Add the item to the container
        jd_container.create_item(body=jdinfo)  #container.upsert_items
        logging.info(f"JD added successfully.status_code=200")
        return True
        
    except Exception as e:
        logging.error(f"Error updating JD in Cosmos Db: {e}")
        return False

# Creating CV entries in CosmosDb
def createCVs(cv_payload):
    try:
        # Check if cv_payload is a string and parse it
        if isinstance(cv_payload, str):
            cv_payload = cv_payload #json.dumps(cv_payload)
        
        # Ensure cv_payload is a list
        if not isinstance(cv_payload, list):
            raise ValueError("cv_payload should be a list of dictionaries")

        cvinfoList = cv_payload

        # Add the item to the container
        for cvinfo in cvinfoList :
            cv_container.create_item(body=cvinfo)  #container.upsert_items
        return True    
   
    except Exception as e:
        logging.error(f"Error updating CV : {e}")
        return False

# Querying CV entries in CosmosDb    
def queryCVs(blob_names):  
    try:
        names_to_find = []
        for blob in blob_names:
            name_to_find = blob.split('.')[0].lower()
            names_to_find.append(name_to_find+'_'+date_str)

        # Query items in Cosmos Db
        query = "SELECT * FROM c WHERE " + " OR ".join([f"c.id LIKE '{item}%'" for item in names_to_find])

        items = list(cv_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))

        # Process the results
        queryResult = []
        for item in items:
            queryResult.append(item)
        return json.dumps(queryResult)
    
    except Exception as e:
        logging.error(f"Error while querying CVs: {e}")
        return False

# Extracting contents from PDF files
def extract_text_from_pdf(path):
    reader = PdfReader(path)
    page = reader.pages[0]
    contents = []
    for page in reader.pages:
        contents.append(page.extract_text())
    contents_text = "\n".join(contents)
    return contents_text  

# Extracting contents from Doc files
# def extract_text_from_docx(file_path):
#     doc = Document(file_path)
#     full_text = []
#     for para in doc.paragraphs:
#         full_text.append(para.text)
#     return '\n'.join(full_text)

# Count tokens in a given CV :
def num_tokens_from_string(string: str, encoding_name: str) -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# Determining the file type
def get_file_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type

def extract_value(pattern, text):
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""

#Convert CV data to formatted Json
def convert_to_json(cv_content, filename):
    # Extract the JSON string from the list
    json_str = cv_content.replace('```', '').replace('\n', '')

    candidate_name = extract_value(r'CandidateName:(.*?)JobTitle', json_str)
    job_title = extract_value(r'JobTitle:(.*?)YearsOfExperience', json_str)
    years_of_experience = extract_value(r'YearsOfExperience:(.*?)PrimarySkills', json_str)
    primary_skills = extract_value(r'PrimarySkills:(.*?)SecondarySkills', json_str)
    secondary_skills = extract_value(r'SecondarySkills:(.*?)ProjectDetails', json_str)
    project_details = extract_value(r'ProjectDetails:(.*?)Education', json_str)
    education = extract_value(r'Education:(.*?)Certifications', json_str)
    certifications = extract_value(r'Certifications:(.*?)$', json_str)

    new_data = {
        'id':  (filename.split('.')[0].replace(' ','_')).lower() + "_" + date_str,
        'cv_name': filename.replace(' ','_'),
        'CandidateName': candidate_name,
        'YearsOfExperience': years_of_experience,
        'JobTitle': job_title,
        'PrimarySkills': primary_skills,
        'SecondarySkills': secondary_skills,
        'ProjectDetails': project_details,
        'Education': education,
        'Certifications': certifications
    }

    cv_json_format = json.dumps(new_data) 
    return json.loads(cv_json_format)

def delTempFolder(folder_path):
    if os.path.exists(folder_path):
    # Delete the folder and all its contents
        shutil.rmtree(folder_path)
        print(f"Folder '{folder_path}' and all its contents have been deleted.")
        return True
    else:
        print(f"Folder '{folder_path}' does not exist.")

# Initialize the app with HTTP triggers
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

#----------------------------- ----- Upload Data in DB ----------------------------------------
@app.route(route="uploadfile", methods=["POST"])
#------------------------------------------------
# 1. Create a tempoary local folder
# 2. Upload the files to the local folder. 
# 3. Extract the contents from CV using prompt
# 4. Upload the extracted content in Cosmos Db
# 5. Upload the JD in Cosmos Db - Need to check
# 6. Delete the tempoary local folder
#------------------------------------------------

def uploadfile(req: func.HttpRequest) -> func.HttpResponse:
    # Step 1: Create a temporary folder if it does not exist
    if not os.path.exists(CV_UPLOAD_FOLDER):
        os.makedirs(CV_UPLOAD_FOLDER)

    try:
        # Get the uploaded files from the request
        files_orig = req.files.getlist("file")  # List of all files
        jd_file = next((file for file in files_orig if file.filename == 'job_description.json'), None)

        # Process job description JSON file, if present
        if jd_file:
            jd_content = jd_file.read().decode('utf-8')
            jd_payload = json.loads(jd_content)
        else:
            print("job_description.json file not found")

        # Remove JD file from list if it was found
        files = [file for file in files_orig if file.filename != 'job_description.json']

        # Check max file upload limit
        if len(files) > MAX_CVS:
            return func.HttpResponse(
                f'Cannot upload more than {MAX_CVS} files at a time', status_code=400
            )

        # Step 2: Upload CVs to the local folder using ThreadPoolExecutor
        def save_file_to_local(file):
            filename = file.filename
            file_content = file.read()
            with open(os.path.join(CV_UPLOAD_FOLDER, filename), 'wb') as f:
                f.write(file_content)
            logging.info(f"File {filename} saved to local folder")

        with ThreadPoolExecutor(max_workers=len(files)) as executor:
            # Submit tasks for each file
            executor.map(save_file_to_local, files)

        # Step 3: Read and extract contents from each CV concurrently
        def process_file(filename):
            file_path = os.path.join(CV_UPLOAD_FOLDER, filename)
            candidate_information = extract_text_from_pdf(file_path)

            evaluation_template1 = """You are an AI recruiter who has to extract relevant information
            from the given candidate's CV and extract its contents.
            Below are the recommended steps for :
            1. Review the {candidate_information} and gather following information -
                a. Name of the candidate
                b. Years of experience - calculate the total years of work experience by summing up the
                    duration of each project or job listed under Work Experience
                c. Job role - Capture the most recent job title held by the candidate
                d. Skills (primary and secondary)- Focus on identifying specific programming languages, 
                software tools, frameworks, and any other technical competencies mentioned
                e. The projects worked on in not more than 40 words for each
                f. Any certifications completed
                g. Education details
                Print your response having following fields. Please do not append serial numbers to them -
                CandidateName:
                JobTitle:
                YearsOfExperience:
                PrimarySkills:
                SecondarySkills:
                ProjectDetails:
                Education:
                Certifications:
            """

            # Count tokens to check the limit
            token_count = num_tokens_from_string(candidate_information, "cl100k_base")
            if token_count < 16000:
                evaluation_prompt_template1 = PromptTemplate(
                    input_variables=["candidate_information"], template=evaluation_template1
                )

                llmchain1 = evaluation_prompt_template1 | llm

                # Generate response from Azure OpenAI
                response1 = llmchain1.invoke(
                    {"candidate_information": candidate_information}
                )
                
                # Format and convert the result
                response1_content = response1.content.replace("\n\n", ", ").replace("\n", "").replace(": ", ":").replace(" - ", " -").replace("   -", " -")
                cv_json_content = convert_to_json(response1_content, filename)
                results1.append(cv_json_content)
            else:
                logging.info(f"{filename} skipped in analysis as token_count exceeded the allowed limit")

        # Process files concurrently
        with ThreadPoolExecutor(max_workers=len(os.listdir(CV_UPLOAD_FOLDER))) as executor:
            executor.map(process_file, os.listdir(CV_UPLOAD_FOLDER))

        # Step 4: Upload extracted content to Cosmos Db
        createCVs(results1)
        logging.info("CVs added successfully. Status_code=200")
        
        # Step 5: Upload the JD in Cosmos Db if available
        if jd_file:
            #job_description = {'id': "JD_" + jd_payload["roleName"] + "_" + time.strftime("%Y%m%d%H%M%S")}
            job_description =  {'id': "JD_"+jd_payload["roleName"]+"_"+time_str}
            jd_payload["roleName"] = jd_payload["roleName"].lower()
            job_description.update(jd_payload)
            createJDs(job_description)
            logging.info("JD uploaded successfully")

        # Step 6: Delete the local folder
        delTempFolder(CV_UPLOAD_FOLDER)

        # Return success response
        return func.HttpResponse(f"All {len(files)} files uploaded successfully.", status_code=200)

    except ValueError:
        return func.HttpResponse("Invalid JSON input", status_code=400)

    except Exception as e:
        logging.error(f"Error uploading files: {e}")
        return func.HttpResponse("Failed to upload files.", status_code=500)

#------------------- Analyze the CV contents for given JD ---------------------------
# 1. Feed the CV payload to LLM for analysis
# 2. Assess the cv contents with given jd to find suitability
#------------------------------------------------------------------------------------
@app.route(route="readfile", methods=['POST'])
def readfile(req: func.HttpRequest) -> func.HttpResponse:
    cvname = None
    x = []
    try:       
        # Retrieve the jd and cv names from the request
        data = req.get_json()
        blob_names = data.get('blob_names')
        job_description = data.get('job_description')
        
        if not blob_names:
            return func.HttpResponse("Please provide cv to be uploaded", status_code=400)
        else:
            # Query CV details from Cosmos DB
            cvQueryData = queryCVs(blob_names)
            cvdata = json.loads(cvQueryData)

            for cv in range(len(blob_names)):
                cvname = blob_names[cv] 
                skill_dict = cvdata[cv]

                candidate_name = skill_dict['CandidateName']
                cv_name = skill_dict["cv_name"]
                yoe = skill_dict["YearsOfExperience"]
                job_title = skill_dict["JobTitle"]
                ps = skill_dict["PrimarySkills"]
                ss = skill_dict["SecondarySkills"]
                project_details = skill_dict["ProjectDetails"]
                certs = skill_dict["Certifications"]

                evaluation_template2="""For given candidate - {candidate_name}, perform the following steps -\
                Step 1: Determine candidate's suitability against given job requirement - {job_description} based on following factors-\
                        Years of experience : {yoe}\
                        Job role : {job_title}  \
                        Skills (primary and secondary)- {ps} and {ss}. \
                            Focus on programming languages, software tools, frameworks, and any other\
                            technical competencies mentioned\
                        Relevant projects worked on - {project_details}\
                        Any certifications completed :{certs} \
                Step 2. Summarize your decision justification in no more than 75 words mentioning exact matching or\
                    missing primary skills.\
                Step 3. Score the candidates on scale of 0-10 based on -\
                    Years of experience - Please adhere strictly to years of experience expected.\
                    Matching technical Skill set - How closely candidate's technical skills align with the\
                        listed skills required.\
                        At least 1 primary skill should match for the candidate to be marked suitable\
                        (e.g., most primary skills matched = 8-10, few primary skills matched = 5-7, very few required skills = 1-4)\
                        Scores can have numbers upto 2 decimal places.\
                Step 4. For Match Suitability - If points assigned are\
                        1-3: Poor match,
                        4-6: Moderate match,
                        7-8: Good Match,
                        9-10: Excellent Match
                Step 5. Determine Suitability - For scores less than 5.00, update the candidate's suitability as not suitable.\
                Expected Output format with each field in a separate line:\
                    Candidate Name: {candidate_name}. This will be header and following will be sub-headers
                     - CV: {cv_name}
                     - Score:
                     - Candidate's Suitability:
                     - Match Level:
                     - Evaluation Justification:
                After evaluation justification ends, please put a horizontal separator before a new candidate starts
                """
                evaluation_prompt_template2=PromptTemplate(
                    input_variables = ["candidate_name", "cv_name", "yoe", "job_title", "ps", "ss", "project_details", "certs", "job_description"], template = evaluation_template2)
                chain2=evaluation_prompt_template2 | llm

                # Generate response from Azure OpenAI
                response2=chain2.invoke(
                    input = {"candidate_name":candidate_name, 
                            "cv_name": cv_name,
                            "yoe":yoe,
                            "job_title":job_title,
                            "ps":ps,
                            "ss":ss,
                            "project_details":project_details,
                            "certs":certs,
                            "job_description": job_description}
                )
                print(f"response2 = {response2.content}")
                results2.append(response2.content)
                        
        # Display the evaluation
        final_response = {
            "response": results2
        }
        final_response_json = json.dumps(final_response)
        return func.HttpResponse(final_response_json)

    except Exception as e:
        logging.error(f"Error reading blob: {e}")
        return func.HttpResponse(f"Failed to read cv data. Error: {str(e)}", status_code=500)

# Querying JD entries in CosmosDb    
@app.route(route="queryJDs", methods=['GET'])
def queryJDs(req: func.HttpRequest) -> func.HttpResponse:
    try:
        roleName = req.params.get('roleName')
        if roleName:
            roleName = roleName.lower()
        else:
            return func.HttpResponse(
                "roleName parameter is missing",
                status_code=400
            )
 
        query = "SELECT * FROM j WHERE j.roleName LIKE '%"+roleName+"%'"
        items = list(jd_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
 
        # Process the results
        queryResult = []
        for item in items:
            queryResult.append(item)
        return func.HttpResponse(json.dumps(queryResult))
   
    except Exception as e:
        logging.error(f"Error while querying JD in Db: {e}")
        return func.HttpResponse(f"Failed to fetch job description from Database. Error: {str(e)}", status_code=500)
    
#------------------------------ Delete files ----------------------------------

@app.route(route="delfile", methods=['POST'])
def deletefile(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Get the delete option from the request (single/all)
        delete_option = req.params.get('delete_option')
        
        if delete_option not in ['single', 'all']:
            return func.HttpResponse("Invalid delete request. Provide 'single' or 'all' in delete_option.", status_code=400)

        # Case 1: Deleting a single record
        if delete_option == 'single':
            record_id = req.params.get('id')
            if not record_id:
                return func.HttpResponse("No record ID provided.", status_code=400)

            # Query for the specific record
            try:
                item = cv_container.read_item(item=record_id, partition_key=PartitionKey(record_id))
                # Deleting the specific record
                cv_container.delete_item(item=item, partition_key=PartitionKey(record_id))
                return func.HttpResponse(f"Record with ID {record_id} deleted successfully.", status_code=200)
            except Exception as e:
                return func.HttpResponse(f"Failed to delete record with ID {record_id}. Error: {str(e)}", status_code=500)

        # Case 2: Deleting all records in the container
        elif delete_option == 'all':
            # Delete all items in the CV container
            try:
                # Query all items in the container (this will fetch all items)
                items = list(cv_container.query_items(
                    query="SELECT * FROM c",
                    enable_cross_partition_query=True
                ))

                # Deleting each record in the container
                for item in items:
                    record_id = item['id']
                    cv_container.delete_item(item=item, partition_key=PartitionKey(record_id))

                return func.HttpResponse("All records deleted successfully.", status_code=200)
            
            except Exception as e:
                logging.error(f"Error deleting all records: {e}")
                return func.HttpResponse(f"Failed to delete records. Error: {str(e)}", status_code=500)

    except Exception as e:
        logging.error(f"Error deleting data from DB: {e}")
        return func.HttpResponse(f"Failed to delete data. Error: {str(e)}", status_code=500)