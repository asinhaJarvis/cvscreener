import streamlit as st
import requests
from datetime import datetime
import pytz
import json
import time
import concurrent.futures

# Azure Function URLs
upload_function_url = "http://localhost:8081/api/uploadfile"
read_function_url = "http://localhost:8081/api/readfile"
delete_function_url = "http://localhost:8081/api/delfile"
query_jds_function_url = "http://localhost:8081/api/queryJDs"

# Function to get the current IST time
def get_current_time_ist():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')

# Set up the page title, icon, and layout for a professional feel
st.set_page_config(page_title="Resume Screener", page_icon="🤖", layout="wide")

# Sidebar title for Navigation
st.sidebar.markdown("<h3 style='color: lightgreen;'>Navigation</h3>", unsafe_allow_html=True)

# Navigation using buttons in the sidebar with unique keys
if st.sidebar.button("Home", key="nav_home"):
    st.session_state.menu = "Home"
if st.sidebar.button("Job Description", key="nav_job_desc"):
    st.session_state.menu = "Job Description"
if st.sidebar.button("Upload Files", key="nav_upload"):
    st.session_state.menu = "Upload Files"
if st.sidebar.button("Analyze", key="nav_analyze"):
    st.session_state.menu = "Analyze"
if st.sidebar.button("Delete Files", key="nav_delete"):
    st.session_state.menu = "Delete Files"

# Task: Updating time every second on the sidebar
st.sidebar.markdown("<h4 style='color: lightgreen;'>Date & Time (IST)</h4>", unsafe_allow_html=True)
placeholder_date = st.sidebar.empty()
placeholder_time = st.sidebar.empty()

# Define functions for each section to be displayed
def home_section():
    st.title("🤖 Resume Screener")
    st.subheader("Automate Your Hiring Process")
    st.markdown(""" 
    This tool leverages AI to screen resumes against given job description, giving you quick insights on candidate's fitment. 
Upload **up to 10 resumes** and fill out the job description form to start the analysis.
""")
    
def job_description_section():
    st.subheader("Job Description")
    role_name = st.text_input("Role Name (max 50 words)", placeholder="Enter the role name (e.g., Software Engineer)")
    st.write(f"{len(role_name.split())}/50 words")
    if len(role_name.split()) > 50:
        st.error("Role name exceeds 50 words.")

    # Option for user to either fetch from Cosmos DB or enter manually
    fetch_from_db = st.radio("Enter job description", 
                             ("Select an existing job description", "Enter manually"))

    if fetch_from_db == "Select an existing job description":
        # Call the Azure Function to fetch job descriptions from Cosmos DB
        if role_name:
            try:
                # Making sure role name is in lowercase before querying
                role_name_lower = role_name.strip().lower()
                response = requests.get(f"{query_jds_function_url}?roleName={role_name_lower}")
                if response.status_code == 200:
                    jd_data = response.json()
                    if jd_data:  # Check if any job descriptions are returned
                        st.subheader("Matching Job Descriptions")
  
                        options = {f"{item['roleName']}_{'_'.join(item['id'].split('_')[-2:])}": item for item in jd_data}
                        selected_option = st.selectbox("Select a role", list(options.keys()))
 
                        if selected_option:
                            selected_role_data = options[selected_option]
                            jd_fetched_dict = json.loads(json.dumps(selected_role_data))
                       
                        # Format the display of JD
                            yoefrom = str(jd_fetched_dict["yearsOfExperience"]["years"])
                            yoeto = str(jd_fetched_dict["yearsOfExperience"]["yearsMax"])
                            ps = ', '.join([str(element) for element in jd_fetched_dict["primarySkill"]])
                            ss = ', '.join([str(element) for element in jd_fetched_dict["secondarySkills"]])
                            #jr = ', '.join([str(element) for element in jd_fetched_dict["jobResponsibilities"]])
                            jr = str(jd_fetched_dict["jobResponsibilities"])
                            jd_fetched_text = "Years of experience :"+yoefrom+" to "+yoeto+" years\nPrimary Skills : \n"+str(ps)+"\nSecondary Skills : \n"+str(ss)+"\nJob Responsibilities : \n"+str(jr)
                            
                            st.text_area("Job Description", value=jd_fetched_text, height=200)
                             
                        # Option to select this JD or fill manually
                        if st.button("Use this Job Description", key="use_from_db"):
                            st.session_state.role_name = selected_role_data['roleName']
                            st.session_state.years_of_experience = (selected_role_data['yearsOfExperience']['years'], selected_role_data['yearsOfExperience']['yearsMax'])
                            st.session_state.primary_skill = selected_role_data['primarySkill']
                            st.session_state.secondary_skills = selected_role_data['secondarySkills']
                            st.session_state.job_responsibilities = selected_role_data['jobResponsibilities']
                            st.success("Job Description saved!.")
                    else:
                        st.error(f"No job description found for role: {role_name_lower}. Please try a different name.")
                else:
                    st.error(f"Failed to fetch job descriptions. Status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching data: {e}")
        else:
            st.error("Please enter a role name to fetch job descriptions.")
    
    # If user chooses to enter manually
    if fetch_from_db == "Enter manually":
        years_of_experience = st.slider("Years of Experience", 0, 20, (0, 5))

        primary_skill = st.text_area("Primary Skills (max 100 words)", placeholder="List primary skills (e.g., Python, ML)")
        st.write(f"{len(primary_skill.split())}/100 words")
        if len(primary_skill.split()) > 100:
            st.error("Primary skills exceed 100 words.")

        secondary_skills = st.text_area("Secondary Skills (max 100 words)", placeholder="List secondary skills")
        st.write(f"{len(secondary_skills.split())}/100 words")
        if len(secondary_skills.split()) > 100:
            st.error("Secondary skills exceed 100 words.")

        job_responsibilities = st.text_area("Job Responsibilities (max 200 words)", placeholder="Describe key responsibilities")
        st.write(f"{len(job_responsibilities.split())}/200 words")
        if len(job_responsibilities.split()) > 200:
            st.error("Job responsibilities exceed 200 words.")

        # Save Job Description Button with unique key
        if st.button("Save Job Description", key="save_job_desc"):
            st.session_state.role_name = role_name
            st.session_state.years_of_experience = years_of_experience
            st.session_state.primary_skill = primary_skill.split(',')
            st.session_state.secondary_skills = secondary_skills.split(',')
            st.session_state.job_responsibilities = job_responsibilities
            st.success("Job description saved!")
        
         # Custom style for the button
    st.markdown(
        """
        <style>
        .stButton>button {
            background-color: #007bff; 
            color: white;
            border-radius: 5px;
            padding: 10px 20px;
            font-size: 16px;
        }
        .stButton>button:hover {
            background-color: #0056b3;
        }
        </style>
        """, 
        unsafe_allow_html=True
    )

    # Step 3: Upload and Analyze Button

def upload_resumes_section():
    st.subheader("Upload Resumes")
    resume_files = st.file_uploader("Upload up to 10 resumes (PDF format)", type="pdf", accept_multiple_files=True)

    if resume_files:
        uploaded_filenames = [resume.name.lower() for resume in resume_files]

        if len(uploaded_filenames) != len(set(uploaded_filenames)):
            st.error("Error: Duplicate file names detected. Please upload files with unique names.")
            return
        
        st.subheader("Uploaded Resumes")
        for resume in resume_files:
            st.write(f"• {resume.name} (Size: {resume.size / 1000:.2f} KB)")

        st.session_state.resume_files = resume_files

    if st.button("Upload Files", key="upload_files") and resume_files:
        files = [('file', (resume.name, resume.read(), resume.type)) for resume in resume_files]

        # Adding job description as JSON payload
        jd_payload = {
            "roleName": st.session_state.get("role_name", ""),
            "yearsOfExperience": {
                "years": st.session_state.get("years_of_experience", (0, 5))[0],
                "yearsMax": st.session_state.get("years_of_experience", (0, 5))[1]
            },
            "primarySkill": st.session_state.get("primary_skill", []),
            "secondarySkills": st.session_state.get("secondary_skills", []),
            "jobResponsibilities": st.session_state.get("job_responsibilities", "")
        }
        files.append(('file', ('job_description.json', json.dumps(jd_payload), 'application/json')))

        try:
            with st.spinner("Uploading files..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(requests.post, upload_function_url, files=files)
                    response = future.result()

            if response.status_code == 200:
                st.success("Files uploaded successfully.")
            else:
                st.error(f"Failed to upload files. Error: {response.status_code}")
        except requests.exceptions.ConnectionError:
            st.error("Connection to the Azure Function failed.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

def analyze_section():
    st.subheader("Analyze")

    # Ensure variables are set in session state
    if 'resume_files' in st.session_state and 'role_name' in st.session_state and 'years_of_experience' in st.session_state:
        resume_files = st.session_state.resume_files
        role_name = st.session_state.role_name
        years_of_experience = st.session_state.years_of_experience

        # Button for analysis with custom styling
        if st.markdown(
            f"<button style='background-color: #007bff; color: white; border: none; padding: 10px 20px; cursor: pointer;'>Analyze</button>",
            unsafe_allow_html=True):
            try:
                analysis_data = {
                    "blob_names": [resume.name for resume in resume_files],
                    "job_description": f"Job Role: {role_name}, Years of Experience: {years_of_experience[0]} - {years_of_experience[1]}"
                }
                with st.spinner("Fetching analysis results..."):
                    response = requests.post(read_function_url, json=analysis_data)
                if response.status_code == 200:
                    st.success("Analysis completed successfully!")
                    
                    # Process the response and format it for display
                    results = response.json().get("response", [])
                    formatted_results = ""
                    for result in results:
                        formatted_results += f"• {result.replace('**', '**')}\n\n"  # Highlighted text
                        
                    st.markdown(formatted_results)
                else:
                    st.error(f"Failed to fetch results. Error: {response.status_code} - {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Failed to connect to the Azure Function. Please ensure it's running.")
            except Exception as e:
                st.error(f"An error occurred: {e}")
    else:
        st.error("Please upload resumes and provide job description details first.")

def delete_files_section():
    st.subheader("Delete Files")
    
    # Choose an option to delete files
    delete_option = st.radio("Choose an option to delete files", ('Delete a specific file', 'Delete all files'))

    # Case for deleting a specific file
    if delete_option == 'Delete a specific file':
        selected_file = st.text_input("Enter the file name to delete (e.g., filename.pdf)")
        if st.button(f"Delete {selected_file}", key="delete_specific"):
            try:
                with st.spinner(f"Deleting {selected_file}..."):
                    response = requests.post(delete_function_url, params={"delete_option": "single", "filename": selected_file})
                    
                if response.status_code == 200:
                    st.success(f"File {selected_file} deleted successfully.")
                elif response.status_code == 404:
                    st.error(f"File {selected_file} not found. Error: {response.status_code}")
                else:
                    st.error(f"Failed to delete {selected_file}. Error: {response.status_code} - {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Connection to the Azure Function failed.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

    # Case for deleting all files
    elif delete_option == 'Delete all files':
        if st.button("Delete all files", key="delete_all"):
            try:
                with st.spinner("Deleting all files..."):
                    response = requests.post(delete_function_url, params={"delete_option": "all"})
                    
                if response.status_code == 200:
                    st.success("All files deleted successfully.")
                else:
                    st.error(f"Failed to delete files. Error: {response.status_code} - {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Connection to the Azure Function failed.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

# Main logic for rendering sections based on the selected menu option
if 'menu' not in st.session_state:
    st.session_state.menu = "Home"

if st.session_state.menu == "Home":
    home_section()
elif st.session_state.menu == "Job Description":
    job_description_section()
elif st.session_state.menu == "Upload Files":
    upload_resumes_section()
elif st.session_state.menu == "Analyze":
    analyze_section()
elif st.session_state.menu == "Delete Files":
    delete_files_section()

# Footer section displayed to users
st.markdown("""--- For more information on how the Resume Screener works, check out the documentation.""")

# Update time display in sidebar every second
while True:
    placeholder_date.markdown(f"**Date:** {get_current_time_ist().split()[0]}")
    placeholder_time.markdown(f"**Time:** {get_current_time_ist().split()[1]}")
    time.sleep(1)