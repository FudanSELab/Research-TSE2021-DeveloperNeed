import os
import re
import zipfile
from pathlib import Path
from xml.etree.ElementTree import parse
import gensim
import spacy
from bs4 import BeautifulSoup
from discussion.api_recognition.base import SOPostAPIRecognition
from discussion.api_recognition.text_based.linker import TextBasedSOPostAPILinker
from discussion.model.base import SOPost


class TextBasedSOPostAPIRecognition(SOPostAPIRecognition):
    CODE_FRAGMENT_MARK = "-CODE-"
    JAVA_KEY_WORDS = ["abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
                      "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
                      "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native",
                      "new", "package", "private", "protected", "public", "return", "strictfp", "short", "static",
                      "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void",
                      "volatile", "while"]
    pattern = re.compile(r'\s+')
    api_patterns = [
        re.compile(r'^(?P<ELE>[a-zA-Z0-9_]*[a-z0-9][A-Z][a-z]+[a-zA-Z0-9_]*)(<.*>)?$'),
        re.compile(r'^(?P<ELE>[a-zA-Z0-9_\.<>]+)\)[a-zA-Z0-9_\,.<>)]*?$'),
        re.compile(r'^(?P<ELE>[a-zA-Z]{2,}(\.[a-zA-Z0-9_]+)+)(<.*>)?$'),
        re.compile(r'^(?P<ELE>((([a-zA-Z0-9_]{2,})(\.))+)([a-zA-Z0-9_]{2,}))?$'),
        re.compile(r'(([a-z_]+([A-Z])[a-z_]+)+)|(([A-Z_]([a-z_]+))+)')
    ]

    def __init__(self):
        self.linker = TextBasedSOPostAPILinker()
        self.name_util = CodeElementNameUtil()
        nlp = spacy.load('en_core_web_sm')
        CustomizeSpacy.customize_tokenizer_split_single_lowcase_letter_and_period(nlp)
        CustomizeSpacy.customize_tokenizer_merge_hyphen(nlp)
        CustomizeSpacy.customize_tokenizer_merge_dot_upper_letter(nlp)
        CustomizeSpacy.customize_tokenizer_api_name_recognition(nlp)
        nlp.add_pipe(CustomizeSpacy.customize_sentencizer_merge_colon, before="tagger")
        nlp.add_pipe(CustomizeSpacy.pipeline_merge_bracket, name='pipeline_merge_bracket', after='tagger')
        self.nlp = nlp
        self.so_tag_list = list(self.__int_tags().keys())

    def __int_tags(self):
        so_path = os.path.dirname(os.path.abspath(__file__))
        tag_path = str(Path(so_path) / "stackoverflow.com-Tags.zip")
        if os.path.exists(tag_path):
            with zipfile.ZipFile(tag_path, 'r') as z:
                f = z.open('Tags.xml')
            doc = parse(f)
            root = doc.getroot()
            tag_data = []
            for child in root:
                tag_data.append(child.attrib)
            tag_dic = {}
            for item in tag_data:
                tag_dic[item["TagName"].lower()] = item
            return tag_dic
        else:
            return {}

    def recognize(self, post: SOPost, is_completed=False):
        body = post.body
        title = post.title
        oriApiSet = set()
        soup = BeautifulSoup(body, "lxml")
        longCodeTags = soup.find_all(name=["pre", 'blockquote'])

        for tag in longCodeTags:
            tag.string = " " + self.CODE_FRAGMENT_MARK + " . \n"

        codeTags = soup.find_all(name="code")
        for tag in codeTags:
            if tag.string == " " + self.CODE_FRAGMENT_MARK + " . \n" or not tag.get_text():
                continue
            if len(tag.get_text()) > 2 and tag.get_text() not in self.JAVA_KEY_WORDS:
                if len(tag.get_text().split("(")[0]) < 3:
                    continue
                oriApiSetFromCodeTag = self.extract_api_from_sentence(tag.get_text())
                oriApiSet.update(oriApiSetFromCodeTag)
        cleanText = soup.get_text()
        decode_clean_text = gensim.utils.decode_htmlentities(cleanText)
        decode_clean_text = re.sub(self.pattern, " ", decode_clean_text.replace('\n', ' ').replace(u'\u00a0', " "))

        doc = self.nlp(decode_clean_text)
        for sen in doc.sents:
            api_from_body = self.extract_api_from_sentence(sen.text)
            oriApiSet.update(api_from_body)

        api_from_title = self.extract_api_from_sentence(title, is_title=True)
        oriApiSet.update(api_from_title)
        if is_completed:
            api_qualified_name = []
            api_dic = {}
            for api in oriApiSet:
                if api.__contains__('#'):
                    tmp_api = api.replace('#', '.')
                    completed_api = self.linker.link_one(post, tmp_api)
                else:
                    completed_api = self.linker.link_one(post, api)
                if completed_api == api and api.lower() in self.so_tag_list:
                    continue
                if len(completed_api.split(".")) == 1 and len(completed_api.split("(")) == 1:
                    continue
                api_dic[api] = completed_api
            soup2 = BeautifulSoup(body, "lxml")
            cleanText2 = soup2.get_text()
            decode_clean_text2 = gensim.utils.decode_htmlentities(cleanText2)
            decode_clean_text2 = re.sub(self.pattern, " ", decode_clean_text2.replace('\n', ' ').replace(u'\u00a0', " "))
            doc2 = self.nlp(decode_clean_text2)
            for key in api_dic:
                sentence = []
                for sen in doc2.sents:
                    if key in sen.text:
                        sentence.append(sen.text)
                if key in title:
                    sentence.append(title)
                api_qualified_name.append({"ori_api": key,
                                           "qualified_name": api_dic[key],
                                           "alias": self.name_util.generate_aliases(api_dic[key]),
                                           "sentence": sentence,
                                           "processed_sentence": sentence})
            return api_qualified_name

        return oriApiSet

    def extract_api_from_sentence(self, sentence: str, is_title=False, is_completed=False):
        oriApiSet = set()
        punc_pattern = r' |,|/|;|\'|`|\[|\]|<|>|\?|:|"|\{|\}|\~|!|@|#|\$|%|\^|&|-|=|\+|，|。|、|；|‘|’|【|】|·|！| ' \
                       r'|…|（|）'
        raw_words = [word for word in re.split(punc_pattern, sentence) if word]
        if not raw_words:
            return oriApiSet
        if is_title and "vs" in sentence.lower():
            raw_words = raw_words
        else:
            if raw_words[0][0].isupper():
                raw_words = raw_words[1:]
        words = []
        for raw_word in raw_words:
            words.append(raw_word.strip())
        words = set(filter(lambda x: x != '', words))
        for word in words:
            if len(word) < 4:
                continue
            if word.endswith("()"):
                oriApiSet.add(word)
                continue
            if word.startswith("(") or word.startswith(")") or word.startswith("www") or word.endswith("com"):
                continue
            if not word[0].isalpha():
                continue

            url_name = re.match(r"[^[/|\\]+([/|\\][^ ]*)", word)
            if url_name:
                continue

            if ("(" in word and ")" not in word) or (")" in word and "(" not in word):
                continue

            if not bool(re.search('[a-z]', word.lower())):
                continue
            if word.endswith("."):
                word = word[:-1]

            for index, pattern in enumerate(self.api_patterns):
                search_rs = pattern.search(word)
                if search_rs is not None:
                    oriApiSet.add(word)
        if is_completed:
            post = SOPost(body=None, title=None)
            oriApiSet_new=set()
            for api in oriApiSet:
                completed_api = self.linker.link_one(post, api)
                if completed_api==api and api.lower() in self.so_tag_list:
                    continue
                if len(completed_api.split(".")) == 1 and len(completed_api.split("(")) == 1:
                    continue
                oriApiSet_new.add(api)
            return oriApiSet_new
        return oriApiSet
