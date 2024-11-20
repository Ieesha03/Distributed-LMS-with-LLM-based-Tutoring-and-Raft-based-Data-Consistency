import sys
import os
#from connection_manager import send_request  # Import the connection utility

# Add the current directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'protos'))





import grpc
from protos import lms_pb2
from protos import lms_pb2_grpc

def view_logs(stub, token):
    try:
        response = stub.get_logs(lms_pb2.LogRequest(token=token))
        if response.status == "success":
            print("Log entries on the current server:")
            for log in response.logs:
                print(f"Index: {log.index}, Command: {log.command}, Term: {log.term}")
        else:
            print("Failed to retrieve logs.")
    except grpc.RpcError as e:
        print(f"Error while retrieving logs: {e}")





def instructor_menu(stub):
    while True:
        print("\nInstructor Menu:")
        print("1. Register")
        print("2. Login")
        print("3. Upload Course Material")
        print("4. View Assignments")
        print("5. Grade Student")
        print("6. Give feedback to the  Student") 
        print("7. View Server Logs")   # New Option
        print("8. Logout")
        print("9. Exit")
        
        choice = input("Select an option: ")

        if choice == "1":
            username = input("Enter username: ")
            password = input("Enter password: ")
            role = "instructor"
            register_response = stub.register(lms_pb2.RegisterRequest(username=username, password=password, role=role))
            print(register_response.status)

        elif choice == "2":
            username = input("Enter username: ")
            password = input("Enter password: ")
            login_response = stub.login(lms_pb2.LoginRequest(username=username, password=password))
            if login_response.status == "success":
                print(f"Instructor logged in with token: {login_response.token}")
                token = login_response.token

                while True:
                    print("\nLogged in as Instructor")
                    print("1. Upload Course Material")
                    print("2. View Assignments")
                    print("3. Grade Student")
                    print("4. Give feedback to the  Student") 
                    print("5. View Server Logs")   # New Option
                    print("6. Logout")
                    print("7. Exit")
                    
                    sub_choice = input("Select an option: ")

                    if sub_choice == "1":
                        file_path = input("Enter the path to the course material PDF: ")
                        with open(file_path, 'rb') as f:
                            data = f.read()
                        post_response = stub.post(lms_pb2.PostRequest(token=token, type="course_material", data=data))
                        print(post_response.status)

                    elif sub_choice == "2":
                        get_response = stub.get(lms_pb2.GetRequest(token=token, type="assignment"))
                        print(f"Assignments: {len(get_response.items)} found.")
                        for item in get_response.items:
                            with open(f"assignment_{item.id}.pdf", 'wb') as f:
                                f.write(item.data)
                            print(f"Saved assignment from {item.id}.")

                    elif sub_choice == "3":
                        student_id = input("Enter the student name to grade: ")
                        grade = input("Enter the grade to assign: ")
                        grade_response = stub.gradeStudent(lms_pb2.GradeRequest(token=token, student_id=student_id, grade=grade))
                        print(grade_response.status)



                    elif sub_choice == "4":
                          student_id = input("Enter the student name to give feedback: ")  # Prompt for student name
                          feedback_message = input("Enter the feedback message: ")  # Prompt for feedback message
                        # Call the RPC to send feedback
                          feedback_response = stub.giveFeedback(lms_pb2.FeedbackRequest(token=token, student_id=student_id, feedback=feedback_message))
                          print(feedback_response.status)
                          
                    elif sub_choice == "5":
                        view_logs(stub, token)   

                    elif sub_choice == "6":
                        logout_response = stub.logout(lms_pb2.LogoutRequest(token=token))
                        print("Logged out.")
                        break
                    
                    elif sub_choice == "7":
                        print("Exiting.")
                        return
                    
                    else:
                        print("Invalid option. Please try again.")

            else:
                print("Instructor login failed.")

        elif choice == "9":
            print("Exiting.")
            break

        else:
            print("Invalid option. Please try again.")

def run():
    servers = ['localhost:50051', 'localhost:50052', 'localhost:50053']
    token = None

    for server in servers:
        try:
            print(f"Connecting to server {server}")
            channel = grpc.insecure_channel(server)
            stub = lms_pb2_grpc.LMSStub(channel)
            instructor_menu(stub)
            break  # Exit after successfully displaying the menu

        except grpc.RpcError as e:
            print(f"Failed to connect to server {server}: {e}")
            continue  # Try the next server if connection fails


if __name__ == "__main__":
    run()
