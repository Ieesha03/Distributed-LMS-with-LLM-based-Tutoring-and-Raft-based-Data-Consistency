import sys
import argparse

import os
import time
import random



import threading


# Add the current directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'protos'))




import grpc
from concurrent import futures
#import openai
import cohere  # Import the Cohere SDK
from protos import lms_pb2
from protos import lms_pb2_grpc
import os

import nltk
import PyPDF2
import re
from collections import Counter
from nltk.corpus import stopwords
#import PyPDF2
#from gemini import Gemini

# Initialize Cohere client with your API key
cohere_api_key = ''  # Replace with your Cohere API key
co = cohere.Client(cohere_api_key)



# Set your OpenAI API key

# In-memory database for users
users = {}
tokens = {}
assignments = {}
course_materials = {}
grades = {}
feedbacks = {}  # New dictionary to store feedback for students

# Raft-related variables
current_term = 0
voted_for = None
log = []
commit_index = 0
is_leader = False
state = "follower"
votes_received = 0
current_leader = None
election_timer_lock = threading.Lock()
election_timer = None
self_address = None
running = True  # Use this flag to start or stop threads

next_index = {}
match_index = {}
log_lock = threading.Lock()
votes_lock = threading.Lock()
candidate_lock = threading.Lock()
raft_nodes = ["localhost:50051", "localhost:50052", "localhost:50053"]
election_timeout = 30  # Timeout for starting an election
heartbeat_interval = 5  # Interval for sending heartbeats








# Store keywords extracted from assignments and course materials
assignment_keywords = {}
course_material_keywords = {}



# Initialize stop words
nltk.download('stopwords')  # Only run this once to download
stop_words = set(stopwords.words('english'))




# Function to extract keywords from PDF files
def extract_keywords_from_pdf(pdf_path):
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            text += page.extract_text()

    # Tokenize and filter out stopwords
    words = re.findall(r'\b\w+\b', text.lower())
    filtered_words = [word for word in words if word not in stop_words]
    
    return set(filtered_words)









class LMSService(lms_pb2_grpc.LMSServicer):
    
    def __init__(self):
        
        self.run_raft_background_tasks()

    def run_raft_background_tasks(self):
        threading.Thread(target=self.monitor_heartbeat).start()
        threading.Thread(target=self.start_election_timer).start()

    def monitor_heartbeat(self):
        global running, is_leader, current_leader
        while running:
            time.sleep(heartbeat_interval)
            if is_leader:
                print(f"Leader {self_address}: Sending heartbeats.")
                for node in raft_nodes:
                    if node != self_address:
                        threading.Thread(target=self.send_heartbeat, args=(node,)).start()
                        
            else:
             print(f"Follower {self_address}: Waiting for heartbeats.")       

        print(f"Heartbeat monitoring thread for {self_address} has stopped.")          

    def start_election_timer(self):
     if not is_leader:    
       self.reset_election_timer()
       print(f"Election timer started for {self_address}.")  # Start the initial election timer  

    def start_election(self):
        global state, current_term, is_leader, votes_received
        with candidate_lock: 
            if state == "follower":
               state = "candidate"
               with votes_lock:
                 current_term += 1
                 votes_received = 1  # Vote for self
               print(f"Node {self_address}: Starting election for term {current_term}.")
        
        # Request votes from other nodes
        for address in raft_nodes:
            if address != self_address:
                threading.Thread(target=self.send_request_vote, args=(address,)).start()

    def shutdown(self):
     self.stop_threads()
     print(f"Node {self_address}: Shutting down gracefully.")
            

    def stop_threads(self):
     global running
     running = False  # This will cause the threads to exit their loops

    # Cancel the election timer if running
     with election_timer_lock:
         if election_timer is not None:
             election_timer.cancel()            

    def send_request_vote(self, address):
        global votes_received, is_leader, state
        with grpc.insecure_channel(address) as channel:
            stub = lms_pb2_grpc.LMSStub(channel)
            lastLogIndex=len(log) - 1 if len(log) > 0 else -1 
            lastLogTerm = log[lastLogIndex]["term"] if lastLogIndex >= 0 else 0
            request = lms_pb2.RequestVoteMessage(
                from_node=self_address, term=current_term,
                lastLogIndex=lastLogIndex,
                lastLogTerm =lastLogTerm
            )
            try:
                response = stub.requestVote(request)
                if response.voteGranted:
                    with votes_lock:
                        votes_received += 1
                        print(f"Node {self_address}: Vote granted from {address}.")
                    if votes_received > len(raft_nodes) // 2 and not is_leader:
                        with votes_lock:
                            if not is_leader:
                             self.become_leader()
            except grpc.RpcError as e:
                print(f"Node {self_address}: Failed to connect to {address}: {e.details()} (Error: {e.code()})")
                print(f"Retrying connection to {address} in 5 seconds...")
                time.sleep(5) 


    def become_leader(self):
        global state, is_leader,current_leader
        state = "leader"
        is_leader = True
        current_leader =  self_address  # Assuming this node is becoming the leader
        print(f"Node {current_leader}: Became leader for term {current_term}.")
        self.initialize_follower_indices()
        self.log_event("election", current_term, "new leader elected")                                                     

    
   
    
    def log_event(self, event_type, term, message):
        # Log leader election events
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Node {current_leader}: {event_type} - Term: {term} - {message}")
        # Additional logging can be implemented here, e.g., writing to a file

    def initialize_follower_indices(self):
        global next_index, match_index
        for node in raft_nodes:
            if node != current_leader:  # Assuming this node is the leader
                next_index[node] = len(log)
                match_index[node] = 0
        print(f"Leader {current_leader}: Initialized follower indices.")    
       

    def appendEntries(self, request, context):
        global current_term, commit_index, state,is_leader,current_leader
        if request.term < current_term:
            return lms_pb2.AppendEntriesReply(from_node=self_address, to=request.from_node, term=current_term, entryAppended=False, matchIndex=len(log)-1)
        
         # Update term and step down if needed
        print(f"Node {self_address}: Current term = {current_term}, Incoming term = {request.term}")
        if request.term >current_term:
          current_term = request.term
          state = "follower"
          is_leader = False
          current_leader = request.from_node  # Update to the new leader's address
          print(f"Node {self_address}: Stepping down as leader due to higher term received.")

        if state == "follower":
         current_leader = request.from_node
         self.reset_election_timer()
         print(f"Follower {self_address}: Received heartbeat from {request.from_node}. Resetting election timer.")

         # Reset election timer to prevent followers from starting an election if they receive a valid heartbeat
        


        # Check log consistency
        if request.prevIndex != -1:  
           if request.prevIndex >= len(log) or log[request.prevIndex]["term"] != request.prevTerm:

            return lms_pb2.AppendEntriesReply(from_node=self_address, to=request.from_node, term=current_term, entryAppended=False, matchIndex=len(log)-1)

        # Append new entries from the leader
        for entry in request.entries:
            if entry.index >= len(log) or log[entry.index]["command"] != entry.command:
                with log_lock:
                    log.append({"index": entry.index, "command": entry.command, "term": request.term})

        commit_index = min(request.commitIndex, len(log))
        return lms_pb2.AppendEntriesReply(from_node=self_address, to=request.from_node, term=current_term, entryAppended=True, matchIndex=len(log)-1)
    

    def reset_election_timer(self):
      global election_timer,running
      with election_timer_lock:
          if election_timer is not None:
              election_timer.cancel()  # Cancel the existing timer
        # Restart the election timer
          if running  and not is_leader:
           election_timer = threading.Timer(election_timeout + random.uniform(1, 3), self.start_election)
           election_timer.start()
           print(f"Follower {current_leader}: Election timer reset.")

    def send_heartbeat(self, address):
        retry_limit = 5
        retries = 0
        if address == current_leader:
        # Skip sending heartbeat to itself
          return


        while retries < retry_limit:
            try:   
                with grpc.insecure_channel(address,options=[
                    ('grpc.keepalive_time_ms', 20000),  # Send keepalive ping every 10 seconds
                    ('grpc.keepalive_timeout_ms', 30000),  # Wait for 10 seconds before timeout
                    ('grpc.http2.max_pings_without_data', 0),  # Allow pings without data
                    ('grpc.http2.min_time_between_pings_ms', 20000)  
                ]) as channel:
                  stub = lms_pb2_grpc.LMSStub(channel)
                   
                # Ensure log is not empty before accessing it
                  prev_index = len(log) - 1 if log else 0
                  prev_term = log[-1]["term"] if log else current_term-1

                # Log the heartbeat details
                  print(f"Node {current_leader}: Sending heartbeat to {address}: prevIndex={prev_index}, prevTerm={prev_term}, commitIndex={commit_index}, currentTerm={current_term}")

                  request = lms_pb2.AppendEntriesMessage(
                    from_node=current_leader,  # Use the dynamic current leader address
                    to=address,
                    
                    term=current_term,
                    prevIndex=prev_index,
                    prevTerm=prev_term,
                    commitIndex=commit_index,
                    entries=[]
            )
            
                  response = stub.appendEntries(request)
                  if not response.entryAppended:
                    print(f"Node {current_leader}: Failed to send heartbeat to {address}.")
                  return    
            except grpc.RpcError as e:
              print(f"Node {current_leader}: Failed to connect to {address}: {e}")
              retries += 1
              print(f"Attempt {retries}/{retry_limit} to connect to {address} failed.")
              if retries < retry_limit:
                print(f"Retrying connection to {address} in 5 seconds...")
                time.sleep(3)
              else:
                print(f"Giving up on sending heartbeat to {address} after {retry_limit} attempts.")
                return

    def run_raft_background_tasks(self):
     threading.Thread(target=self.monitor_heartbeat, daemon=True).start()
     threading.Thread(target=self.start_election_timer, daemon=True).start()
            
                

    def redirect_to_leader(self, log_entry):
      global current_leader
      retries = 5  # Set a retry limit
      while retries > 0:
          try:
              leader_address = current_leader  # Get the current leader address
              print(f"Redirecting to new leader at {leader_address}")
              with grpc.insecure_channel(leader_address) as channel:
                  stub = lms_pb2_grpc.LMSStub(channel)
                  request = lms_pb2.LogEntry(index=len(log), command=log_entry["command"])
                  response = stub.appendEntries(request)
                  if response.entryAppended:
                      print(f"Node {self_address}: Successfully forwarded request to leader {current_leader}.")
                      return True
                  else:
                     print(f"Node {self_address}: Failed to forward request to leader {current_leader}.")
                     return False

                      
             
          except grpc.RpcError:
              print(f"Failed to connect to leader at {leader_address}, retrying...")
              retries -= 1
              time.sleep(2)  # Wait before retrying
      print("Failed to forward request after retries.")
      return False
          

    def append_entry_to_log(self, log_entry):
        global is_leader, commit_index
        if not is_leader:
            # If not leader, redirect to leader
            print(f"Node {self_address}: Not the leader. Forwarding request to leader {current_leader}.")
            print("Not the leader. Redirecting request to the leader.")
            self.redirect_to_leader(log_entry)
            return False

        with log_lock:
            log.append(log_entry)
            commit_index = len(log) - 1

        # Attempt to replicate the log entry to followers
        success_count = 1  # Leader itself
        for node in raft_nodes:
            if node != current_leader:  # Replace with leader's address if needed
                if self.replicate_log_to_follower(node, log_entry):
                    success_count += 1

        # Confirm commit only if a majority has been successful
        if success_count >= len(raft_nodes) // 2:
            print(f"Log entry committed. Term: {current_term}, Index: {commit_index}")
            return True

        print("Failed to reach consensus for log entry. Rolling back.")
        with log_lock:
          log.pop()  # Rollback on failure
        return False
    


    def replicate_log_to_follower(self, address, log_entry):
        with grpc.insecure_channel(address) as channel:
            stub = lms_pb2_grpc.LMSStub(channel)
            prevIndex = len(log) - 2 if len(log) > 1 else -1
            prevTerm = log[prevIndex]["term"] if prevIndex >= 0 else current_term - 1
            request = lms_pb2.AppendEntriesMessage(
                from_node=current_leader,
                to=address,
                term=current_term,
                prevIndex=prevIndex,
                prevTerm=prevTerm,
                commitIndex=commit_index,
                entries=[lms_pb2.LogEntry(index=len(log) - 1, command=log_entry["command"])]
            )
            try:
                response = stub.appendEntries(request)
                if response.entryAppended:
                 print(f"Node {current_leader}: Log entry '{log_entry['command']}' replicated successfully to {address}.")
                else:
                 print(f"Node {current_leader}: Failed to replicate log entry '{log_entry['command']}' to {address}.")
                
                return response.entryAppended
            except grpc.RpcError as e:
                print(f"Failed to replicate log to {address}: {e}")
                return False            
            
    def sync_logs_with_followers(self):
     for node in raft_nodes:
        if node != current_leader:  # Assuming this node is the leader
            self.replicate_log_to_follower(node)
    
    def requestVote(self, request, context):
     global current_term, voted_for
     if request.term > current_term:
        current_term = request.term
        voted_for = None

     if (voted_for is None or voted_for == request.from_node) and (request.term >= current_term):
        voted_for = request.from_node
        return lms_pb2.RequestVoteReply(from_node=self_address, to=request.from_node, term=current_term, voteGranted=True)
     return lms_pb2.RequestVoteReply(from_node=self_address, to=request.from_node, term=current_term, voteGranted=False)
    


    def forward_to_leader(self, request, method_name):
      global current_leader
      try:
          with grpc.insecure_channel(current_leader) as channel:
              stub = lms_pb2_grpc.LMSStub(channel)
            # Dynamically forward the request using the specified method
              method = getattr(stub, method_name)
              response = method(request)
              print(f"Node {self_address}: Successfully forwarded {method_name} request to leader {current_leader}.")
              return response
      except grpc.RpcError as e:
          print(f"Node {self_address}: Error forwarding {method_name} request to leader {current_leader}: {e.details()}")
          return lms_pb2.StatusResponse(status="failure")

    def get_logs(self, request, context):
        # Check if the token is valid
        if request.token not in tokens:
            return lms_pb2.LogResponse(status="failure", logs=[])

        with log_lock:  # Ensure thread-safe access to logs
            log_entries = [
                lms_pb2.LogEntry(command=entry["command"], term=entry["term"], index=entry["index"])
                for entry in log
            ]
            return lms_pb2.LogResponse(status="success", logs=log_entries)
        
        



    

   

    def register(self, request, context):
        if request.username in users:
            return lms_pb2.StatusResponse(status="Username already exists.")
        users[request.username] = request.password
        return lms_pb2.StatusResponse(status="Registration successful.")

    def login(self, request, context):
        if request.username in users and users[request.username] == request.password:
            token = f"token-{request.username}"
            tokens[token] = request.username
            return lms_pb2.LoginResponse(status="success", token=token)
        return lms_pb2.LoginResponse(status="failure", token="")

    def logout(self, request, context):
        if request.token in tokens:
            del tokens[request.token]
            return lms_pb2.StatusResponse(status="success")
        return lms_pb2.StatusResponse(status="failure")

    def post(self, request, context):
        if request.token not in tokens:
            return lms_pb2.StatusResponse(status="failure")

        user = tokens[request.token]
        file_data = request.data
        file_path = f"./tmp/{user}_{request.type}.pdf"



        # Save the file to the temporary directory
        with open(file_path, 'wb') as f:
            f.write(file_data)
        




        if request.type == "assignment":
            assignment_keywords[user] = extract_keywords_from_pdf(file_path)
            assignments[user] = file_data
            return lms_pb2.StatusResponse(status="Assignment uploaded.")
        elif request.type == "course_material":
            course_material_keywords[user] = extract_keywords_from_pdf(file_path)
            course_materials[user] = file_data
            return lms_pb2.StatusResponse(status="Course material uploaded.")
        
        return lms_pb2.StatusResponse(status="Unknown post type.")

    def get(self, request, context):
        if not is_leader:
        # Forward the get request (for grades, feedback, etc.) to the current leader if not the leader
         print(f"Node {self_address}: Not the leader. Forwarding get request to leader {current_leader}.")
         return self.forward_to_leader(request, 'get')
        

        if request.token not in tokens:
            return lms_pb2.GetResponse(status="failure", items=[])
        user = tokens[request.token]

        if request.type == "course_material":
            materials = [lms_pb2.DataItem(id=user, data=pdf) for user, pdf in course_materials.items()]
            return lms_pb2.GetResponse(status="success", items=materials)

        if request.type == "assignment":
            # Return all assignments uploaded by students
            assignments_data = []
            for student, assignment in assignments.items():
                assignments_data.append(lms_pb2.DataItem(id=student, data=assignment))
            return lms_pb2.GetResponse(status="success", items=assignments_data)
        
        if request.type == "feedback":
            if user in feedbacks:
                feedback_data = feedbacks[user].encode("utf-8")
                print(f"Attempted to get feedback non-existent student:")
        
                return lms_pb2.GetResponse(status="success", items=[lms_pb2.DataItem(id=user, data=feedback_data)])
                
        
    
           
              
        
        
        
      
        
        
        
        if request.type == "grades":
            if user in grades:
                grade_data = grades[user].encode("utf-8")
                return lms_pb2.GetResponse(status="success", items=[lms_pb2.DataItem(id=user, data=grade_data)])
                
            
        
        return lms_pb2.GetResponse(status="failure", items=[])
    
        
    

    # Validate question based on extracted keywords
    def validate_question(self, question, assignment_keywords, coursework_keywords):
        question_words = set(re.findall(r'\b\w+\b', question.lower()))
        # Check if any keyword from the question matches assignment or coursework keywords
        if question_words.intersection(assignment_keywords) or question_words.intersection(coursework_keywords):
            return True
        return False





    def askQuestion(self, request, context):
        # Check if the question is in the context of the assignment or course material
        user = tokens.get(request.token)
        if not user:
            return lms_pb2.AnswerResponse(status="failure", answer="Unauthorized access.")
        


        # Get the keywords for the assignment and coursework for this user
        assignment_keys = assignment_keywords.get(user, set())
        coursework_keys = course_material_keywords.get(user, set())




         # Validate the question based on the keywords
        if not self.validate_question(request.question, assignment_keys, coursework_keys):
            return lms_pb2.AnswerResponse(status="failure", answer="Not a valid question.")
         # Make API call to Cohere instead of OpenAI
        response = co.generate(
            model='command',  # Cohere's available model
            prompt=request.question,
            max_tokens=200,  # Adjust tokens as needed
            temperature=0.5
        )
        
        answer = response.generations[0].text




        
        
       
        return lms_pb2.AnswerResponse(status="success", answer=answer)

    def gradeStudent(self, request, context):
        if not is_leader:
        # Forward the grading request to the current leader if not the leader
         print(f"Node {self_address}: Not the leader. Forwarding gradeStudent request to leader {current_leader}.")
         return self.forward_to_leader(request, 'gradeStudent')



        print(f"Current leader is: {current_leader}")

        if request.token not in tokens:
            return lms_pb2.StatusResponse(status="failure")
        print("Current registered users:", users)
        if request.student_id not in users:
            print(f"Attempted to grade non-existent student: {request.student_id}")
            return lms_pb2.StatusResponse(status="Student does not exist.")


         # Store the grade for the student
        log_entry = {
            "command": f"grade:{request.student_id}:{request.grade}",
            "term": current_term
        }
        if self.append_entry_to_log(log_entry):
            grades[request.student_id] = request.grade
            return lms_pb2.StatusResponse(status="Grade assigned successfully.")
        return lms_pb2.StatusResponse(status="Failed to assign grade.")
    


    def giveFeedback(self, request, context):
        if not is_leader:
        # Forward the feedback request to the current leader if not the leader
          print(f"Node {self_address}: Not the leader. Forwarding giveFeedback request to leader {current_leader}.")
          return self.forward_to_leader(request, 'giveFeedback')
        

        print(f"Current leader is: {current_leader}")

        if request.token not in tokens:
            return lms_pb2.StatusResponse(status="failure")
        print("Current registered users:", users)
        if request.student_id not in users:
            print(f"Attempted to give feedback to non-existent student: {request.student_id}")
            return lms_pb2.StatusResponse(status="Student does not exist.")


        # Store feedback for the student
        log_entry = {
            "command": f"feedback:{request.student_id}:{request.feedback}",
            "term": current_term
        }
        if self.append_entry_to_log(log_entry):
            feedbacks[request.student_id] = request.feedback
            return lms_pb2.StatusResponse(status="Feedback given successfully.")
        return lms_pb2.StatusResponse(status="Failed to give feedback.")
    
  

def serve(port):
    global self_address
    self_address = f"localhost:{port}"  # Dynamically set the self address based on the port
    print(f"Self address is set to: {self_address}")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    lms_pb2_grpc.add_LMSServicer_to_server(LMSService(), server)
    server.add_insecure_port(f'[::]:{port}')  # Use the specified port
    server.start()
    print(f"LMS Server started on port {port} with address {self_address}.")
    server.wait_for_termination()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run LMS server.')
    parser.add_argument('--port', type=int, default=50051, help='Port number to run the server on')
    args = parser.parse_args()
    serve(args.port)     
    try:
        serve(args.port)
    except KeyboardInterrupt:
        print("Shutting down server due to KeyboardInterrupt...")  