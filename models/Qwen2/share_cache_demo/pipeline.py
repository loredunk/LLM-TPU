import argparse

import chat
import json
import time
from transformers import AutoTokenizer


class Qwen:
    def __init__(self, args):
        # preprocess parameters, such as prompt & tokenizer
        # devid
        self.devices = [int(d) for d in args.devid.split(",")]
        self.model_list = [d for d in args.model_path_list.split(",")]

        # load tokenizer
        print("Load " + args.tokenizer_path + " ...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            args.tokenizer_path, trust_remote_code=True
        )

        # warm up
        self.tokenizer.decode([0])
        self.EOS = self.tokenizer.eos_token_id

        self.model = chat.Qwen()
        self.init_params(args)

    def load_model(self, model_path):
        load_start = time.time()
        self.model.init(self.devices, model_path)
        load_end = time.time()
        print(f"\nLoad Time: {(load_end - load_start):.3f} s")

    def init_params(self, args):
        self.model.temperature = args.temperature
        self.model.top_p = args.top_p
        self.model.repeat_penalty = args.repeat_penalty
        self.model.repeat_last_n = args.repeat_last_n
        self.model.max_new_tokens = args.max_new_tokens
        self.model.generation_mode = args.generation_mode
        self.model.lib_path = args.lib_path

    def stream_answer(self, tokens, inference_mode, max_tok_num):
        """
        Stream the answer for the given tokens.
        """
        tok_num = 0
        self.answer_cur = ""
        self.answer_token = []

        print()
        # First token
        first_start = time.time()
        if inference_mode == "normal":
            token = self.model.forward_first(tokens)
        elif inference_mode == "share":
            token = self.model.forward_unshare(tokens)
        else:
            raise ValueError(f"Not support {inference_mode}")
        first_end = time.time()
        # Following tokens
        while (max_tok_num > 0 and tok_num < max_tok_num) or (
            max_tok_num == 0
            and token != self.EOS
            and self.model.total_length < self.model.SEQLEN
        ):
            word = self.tokenizer.decode(token, skip_special_tokens=True)
            self.answer_token += [token]
            print(word, flush=True, end="")
            tok_num += 1
            token = self.model.forward_next()
        self.answer_cur = self.tokenizer.decode(self.answer_token)

        # counting time
        next_end = time.time()
        first_duration = first_end - first_start
        next_duration = next_end - first_end
        tps = tok_num / next_duration

        print()
        if inference_mode == "normal":
            print(f"FTL Time: {first_duration:.3f} s")
        elif inference_mode == "share":
            print(f"Unshare FTL Time: {first_duration:.3f} s")
        print(f"TPS: {tps:.3f} token/s")

    def read_json(self, json_path, task_id):
        with open(json_path, "r") as file:
            text = json.load(file)
        system_str = "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"

        content_str = ""
        if "content" in text[task_id]:
            content_str = system_str + text[task_id]["content"]
        question_str = text[task_id]["question"] + "<|im_end|>\n<|im_start|>assistant\n"
        return content_str, question_str

    def test_share_cache(self):
        json_path = "../../../assets/sophgo_kv_cache_share_test_case.json"
        share_str, unshare_str_0 = self.read_json(json_path, 0)
        _, unshare_str_1 = self.read_json(json_path, 1)
        _, unshare_str_2 = self.read_json(json_path, 2)
        # share_str = "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"
        # unshare_str_0 = "can you help me<|im_end|>\n<|im_start|>assistant\n"
        # unshare_str_1 = "tell me a love story<|im_end|>\n<|im_start|>assistant\n"
        # unshare_str_2 = "tell me a love story<|im_end|>\n<|im_start|>assistant\n"

        self.model.init_decrypt()
        # ===------------------------------------------------------------===
        # Model 0
        # ===------------------------------------------------------------===
        # load model 0
        self.model.io_alone_mode = 0
        self.load_model(self.model_list[0])

        # share prefill
        share_tokens = self.tokenizer.encode(
            share_str, max_length=8000, truncation=True
        )

        # task 0
        # first + decode
        unshare_tokens = self.tokenizer.encode(unshare_str_0)
        self.stream_answer(share_tokens + unshare_tokens, "normal", 0)


        # task 1
        # first + decode
        unshare_tokens = self.tokenizer.encode(unshare_str_0)
        self.stream_answer(share_tokens + unshare_tokens, "normal", 0)

        self.model.free_device()

        # ===------------------------------------------------------------===
        # Model 1
        # ===------------------------------------------------------------===
        # load model 1
        self.model.io_alone_mode = 0
        self.load_model(self.model_list[1])

        # first + decode
        unshare_tokens = self.tokenizer.encode(unshare_str_0)
        self.stream_answer(share_tokens[:3000] + unshare_tokens, "normal", 0)

        # first + decode
        unshare_tokens = self.tokenizer.encode(unshare_str_0)
        self.stream_answer(share_tokens[:3000] + unshare_tokens, "normal", 0)

        # ===------------------------------------------------------------===
        # Deinit
        # ===------------------------------------------------------------===
        self.model.deinit_decrypt()
        self.model.deinit()



"""
-1: your input is empty or exceed the maximum length
-2: can not to create handle
-3: can not to create bmrt
-4: can not to load bmodel, maybe your key is wrong
-5: can not to inference bmodel
"""
def main(args):

    # normal test
    start_time = time.time()
    model = Qwen(args)
    model.test_share_cache()
    end_time = time.time()
    print(f"\nTotal Time: {(end_time - start_time):.3f} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--model_path_list", type=str, required=True, help="path to the bmodel files")
    parser.add_argument('-t', '--tokenizer_path', type=str, default="../support/token_config", help='path to the tokenizer file')
    parser.add_argument('-d', '--devid', type=str, default='0', help='device ID to use')
    parser.add_argument('--temperature', type=float, default=1.0, help='temperature scaling factor for the likelihood distribution')
    parser.add_argument('--top_p', type=float, default=1.0, help='cumulative probability of token words to consider as a set of candidates')
    parser.add_argument('--repeat_penalty', type=float, default=1.2, help='penalty for repeated tokens')
    parser.add_argument('--repeat_last_n', type=int, default=32, help='repeat penalty for recent n tokens')
    parser.add_argument('--max_new_tokens', type=int, default=1024, help='max new token length to generate')
    parser.add_argument('--generation_mode', type=str, choices=["greedy", "penalty_sample"], default="greedy", help='mode for generating next token')
    parser.add_argument('--prompt_mode', type=str, choices=["prompted", "unprompted"], default="prompted", help='use prompt format or original input')
    parser.add_argument('--enable_history', action='store_true', help="if set, enables storing of history memory")
    parser.add_argument('--lib_path', type=str, default='', help='lib path by user')
    parser.add_argument('--embedding_path', type=str, default='', help='binary embedding path')
    args = parser.parse_args()
    main(args)
