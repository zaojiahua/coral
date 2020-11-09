class JobLink:
    def __init__(self, prev_node_key, next_node_dict):
        self.prev_node_key = prev_node_key
        self.next_node_key = next_node_dict.get("nextNode")
        self.exec_link_dict = next_node_dict.get("checkDict")

    def execute(self):
        pass
