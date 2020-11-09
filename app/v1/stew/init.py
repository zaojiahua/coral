from app.v1.stew.similarity_matrix_monitor import register_stew_user, SimilarityMatrixMonitor

similarity_matrix_monitor_object = None
user_id = 0


def calculate_matrix():
    global user_id
    global similarity_matrix_monitor_object
    user_id = register_stew_user()
    similarity_matrix_monitor_object = SimilarityMatrixMonitor(user_id)
    similarity_matrix_monitor_object.start()
    print("stew init finished ")
