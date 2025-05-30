import os
import shutil
import traceback
from typing import ClassVar

from marin.evaluation.evaluators.evaluator import Dependency, ModelConfig
from marin.evaluation.evaluators.vllm_tpu_evaluator import VllmTpuEvaluator
from marin.evaluation.utils import is_remote_path, upload_to_gcs, write_yaml


class AlpacaEvaluator(VllmTpuEvaluator):
    """
    Evaluator that runs AlpacaEval: https://github.com/tatsu-lab/alpaca_eval

    Ensure OPENAI_API_KEY is set in the environment to use the default auto evaluator:
    "weighted_alpaca_eval_gpt4_turbo", which has a high agreement rate with their human
    annotation data and is relatively cost-efficient.
    Source: https://github.com/tatsu-lab/alpaca_eval?tab=readme-ov-file#quick-start
    """

    CACHE_PATH: str = "/tmp/alpaca-eval"
    BASE_RESULTS_PATH: str = os.path.join(CACHE_PATH, "alpaca_results")

    # AlpacaEval has 805 examples: https://huggingface.co/datasets/tatsu-lab/alpaca_eval/raw/main/alpaca_eval.json
    # so if the number of instances is not specified, we will run on all of them.
    DEFAULT_MAX_INSTANCES: int = 805

    _pip_packages: ClassVar[list[Dependency]] = [*VllmTpuEvaluator.DEFAULT_PIP_PACKAGES, Dependency(name="alpaca-eval")]

    @staticmethod
    def write_model_config_file(model: ModelConfig, path: str) -> None:
        """
        Write out the necessary model configuration files for AlpacaEval

        Args:
            model (ModelConfig): The model configuration
            path (str): Path where to write the config file
            generation_params (dict, optional): Dictionary of generation parameters. Defaults to None.
        """
        model_name_or_path: str = model.name if model.path is None else model.path
        generation_params = model.generation_params
        # Set default parameters if not provided
        if generation_params is None:
            generation_params = {}

        # Default values for generation parameters
        temp = generation_params.get("temperature", 0.7)
        presence_penalty = generation_params.get("presence_penalty", 0.0)
        frequency_penalty = generation_params.get("frequency_penalty", 0.0)
        repetition_penalty = generation_params.get("repetition_penalty", 1.0)
        top_p = generation_params.get("top_p", 1.0)
        top_k = generation_params.get("top_k", -1)
        stop_token_ids = generation_params.get("stop_token_ids", None)
        # On how to write the model configuration file, see
        # https://github.com/tatsu-lab/alpaca_eval/blob/main/src/alpaca_eval/main.py#L241
        content: dict = {
            model_name_or_path.split("/")[-1]: {
                # Could be any arbitrary prompt template but the Cohere one prompts
                # with the just instruction without any prompt engineering: {instruction}
                # https://github.com/tatsu-lab/alpaca_eval/blob/main/src/alpaca_eval/models_configs/cohere/prompt.txt
                "prompt_template": "Mixtral-8x7B-Instruct-v0.1/togetherai_prompt.txt",
                "fn_completions": "vllm_local_completions",
                "completions_kwargs": {
                    "model_name": model_name_or_path,
                    # Mandatory argument for `vllm_local_completions` in AlpacaEval
                    # https://github.com/tatsu-lab/alpaca_eval/blob/main/src/alpaca_eval/decoders/vllm_local.py#L21
                    "max_new_tokens": None,  # Following the config above, set to None to go up to EOS or context length
                    "temperature": temp,
                    "top_p": top_p,
                    "top_k": top_k,
                    "presence_penalty": presence_penalty,
                    "frequency_penalty": frequency_penalty,
                    "repetition_penalty": repetition_penalty,
                    "stop_token_ids": stop_token_ids,
                    "model_kwargs": {
                        "max_model_len": model.engine_kwargs.get("max_model_len", 4096),  # Cap at 4096 tokens
                        "enforce_eager": model.engine_kwargs.get("enforce_eager", False),
                        "dtype": "bfloat16",  # Explicitly use bfloat16 for TPU
                        # "enforce_eager": True, # Uncomment if you want to enforce eager execution to save memory
                        "device": "tpu",
                    },
                    "is_chatml_prompt": True,
                },
            }
        }
        write_yaml(content, path)
        return content

    @staticmethod
    def set_openai_api_key() -> None:
        """
        Set the OPENAI_API_KEY environment variable. We assume the API key is stored in ~/.cache/openai/token.
        """
        # If the environment variable is already set, we don't need to do anything
        if os.environ.get("OPENAI_API_KEY") is not None:
            return

        with open(os.path.expanduser("~/.cache/openai/token"), "r") as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    def evaluate(
        self,
        model: ModelConfig,
        evals: list[str],
        output_path: str,
        max_eval_instances: int | None = None,
    ) -> None:
        """
        Runs AlpacaEval on the specified model.

        Args:
            model (ModelConfig): The model configuration of the model we want to evaluate
            evals (List[str]): Does nothing. We just run on the default eval set.
            output_path (str): The path to save the evaluation results.
            max_eval_instances (int | None): The maximum number of evaluation instances to run.
        """
        try:
            # Set the OPENAI_API_KEY environment variable for the auto evaluator
            self.set_openai_api_key()

            # Download the model from GCS or HuggingFace
            model_name_or_path: str = self.download_model(model)

            model_config_path: str = os.path.join(AlpacaEvaluator.CACHE_PATH, model_name_or_path, "model_config.yaml")
            model_config_content = self.write_model_config_file(model, model_config_path)

            # Construct the command and run AlpacaEval
            max_eval_instances = max_eval_instances or self.DEFAULT_MAX_INSTANCES
            model_name = os.path.basename(model_name_or_path)
            results_path: str = os.path.join(AlpacaEvaluator.BASE_RESULTS_PATH, model_name)

            from alpaca_eval import evaluate_from_model

            # We don't want to overload the vLLM inference engine or else we will have to recompute the cache
            if max_eval_instances is None or max_eval_instances == AlpacaEvaluator.DEFAULT_MAX_INSTANCES:
                evaluate_from_model(
                    model_configs=model_config_content,
                    output_path=results_path,
                    chunksize=64,
                )
            else:
                evaluate_from_model(
                    model_configs=model_config_content,
                    output_path=results_path,
                    max_instances=max_eval_instances,
                )

            # Upload the results to GCS
            if is_remote_path(output_path):
                upload_to_gcs(local_path=results_path, gcs_path=output_path)
        except Exception as e:
            traceback.print_exc()
            raise RuntimeError("AlpacaEval failed. Please check the logs for more information.") from e
        finally:
            self.cleanup(model)
            shutil.rmtree(AlpacaEvaluator.BASE_RESULTS_PATH, ignore_errors=True)
