from discussion.api_recognition.code_based.baker.base import BakerBaseClass


class CodeBasedWithNeo4jBaker(BakerBaseClass):
    def __init__(self, graph_client, graph=None):
        super().__init__(graph=graph, graph_client=graph_client)

    def baker(self, code):
        class_recognitions, false_classes = self.extract_class_from_code(code)
        method_recognitions, class_object_pair = self.extract_method_from_code(code)
        class_method_dic = {}
        for class_recognition in class_recognitions:
            class_method_dic[class_recognition] = []
        for method_recognition in method_recognitions:
            class_method_dic.setdefault(method_recognition.split('.')[0], []).append(method_recognition.split('.')[-1])
        locate_class_method_dic = self.locate_api(code, class_method_dic)
        api_qualified_name = self.neo4j_based_linker(locate_class_method_dic, class_object_pair)
        return api_qualified_name
