from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Callable

from checkov.common.output.record import Record
from checkov.common.output.report import Report
from checkov.common.bridgecrew.check_type import CheckType
from checkov.common.parallelizer.parallel_runner import parallel_runner
from checkov.common.runners.base_runner import BaseRunner, filter_ignored_paths
from checkov.common.util.dockerfile import is_docker_file
from checkov.common.typing import _CheckResult
from checkov.dockerfile.parser import parse, collect_skipped_checks
from checkov.dockerfile.registry import registry
from checkov.runner_filter import RunnerFilter

if TYPE_CHECKING:
    from checkov.common.parsers.node import DictNode
    from checkov.dockerfile.base_dockerfile_check import BaseDockerfileCheck


class Runner(BaseRunner):
    check_type = CheckType.DOCKERFILE  # noqa: CCE003  # a static attribute

    def should_scan_file(self, filename: str) -> bool:
        return is_docker_file(os.path.basename(filename))

    def run(
        self,
        root_folder: str | None = None,
        external_checks_dir: list[str] | None = None,
        files: list[str] | None = None,
        runner_filter: RunnerFilter | None = None,
        collect_skip_comments: bool = True,
    ) -> Report:
        runner_filter = runner_filter or RunnerFilter()
        if not runner_filter.show_progress_bar:
            self.pbar.turn_off_progress_bar()

        report = Report(self.check_type)
        files_list = []
        filepath_fn = None
        if external_checks_dir:
            for directory in external_checks_dir:
                registry.load_external_checks(directory)

        if files:
            files_list = [file for file in files if is_docker_file(os.path.basename(file))]

        if root_folder:
            filepath_fn = lambda f: f'/{os.path.relpath(f, os.path.commonprefix((root_folder, f)))}'
            for root, d_names, f_names in os.walk(root_folder):
                filter_ignored_paths(root, d_names, runner_filter.excluded_paths)
                filter_ignored_paths(root, f_names, runner_filter.excluded_paths)
                for file in f_names:
                    if is_docker_file(file):
                        file_path = os.path.join(root, file)
                        files_list.append(file_path)

        definitions, definitions_raw = get_files_definitions(files_list, filepath_fn)
        self.pbar.initiate(len(definitions))
        for docker_file_path in definitions.keys():
            self.pbar.set_additional_data({'Current File Scanned': os.path.relpath(docker_file_path, root_folder)})
            # There are a few cases here. If -f was used, there could be a leading / because it's an absolute path,
            # or there will be no leading slash; root_folder will always be none.
            # If -d is used, root_folder will be the value given, and -f will start with a / (hardcoded above).
            # The goal here is simply to get a valid path to the file (which docker_file_path does not always give).
            if docker_file_path[0] == '/':
                path_to_convert = (root_folder + docker_file_path) if root_folder else docker_file_path
            else:
                path_to_convert = (os.path.join(root_folder, docker_file_path)) if root_folder else docker_file_path

            file_abs_path = os.path.abspath(path_to_convert)
            report.add_resource(file_abs_path)
            skipped_checks = collect_skipped_checks(definitions[docker_file_path])
            instructions = definitions[docker_file_path]

            results = registry.scan(docker_file_path, instructions, skipped_checks, runner_filter)

            for check, check_result in results.items():
                result_configuration = check_result['results_configuration']
                startline = 0
                endline = len(definitions_raw[docker_file_path]) - 1
                result_instruction = ""
                if result_configuration:
                    if isinstance(result_configuration, list):
                        for res in result_configuration:
                            startline = res['startline']
                            endline = res['endline']
                            result_instruction = res["instruction"]
                            self.build_record(report,
                                              definitions_raw,
                                              docker_file_path,
                                              file_abs_path,
                                              check,
                                              check_result,
                                              startline,
                                              endline,
                                              result_instruction)
                    else:
                        startline = result_configuration['startline']
                        endline = result_configuration['endline']
                        result_instruction = result_configuration["instruction"]
                        self.build_record(report,
                                          definitions_raw,
                                          docker_file_path,
                                          file_abs_path,
                                          check,
                                          check_result,
                                          startline,
                                          endline,
                                          result_instruction)
                else:
                    self.build_record(report,
                                      definitions_raw,
                                      docker_file_path,
                                      file_abs_path,
                                      check,
                                      check_result,
                                      startline,
                                      endline,
                                      result_instruction)
            self.pbar.update()
        self.pbar.close()
        return report

    def calc_record_codeblock(
        self,
        codeblock: list[tuple[int, str]],
        definitions_raw: dict[str, list[str]],
        docker_file_path: str,
        endline: int,
        startline: int,
    ) -> None:
        for line in range(startline, endline + 1):
            codeblock.append((line + 1, definitions_raw[docker_file_path][line]))

    def build_record(
        self,
        report: Report,
        definitions_raw: dict[str, list[str]],
        docker_file_path: str,
        file_abs_path: str,
        check: BaseDockerfileCheck,
        check_result: _CheckResult,
        startline: int,
        endline: int,
        result_instruction: str,
    ) -> None:
        codeblock: list[tuple[int, str]] = []
        self.calc_record_codeblock(codeblock, definitions_raw, docker_file_path, endline, startline)
        record = Record(
            check_id=check.id,
            bc_check_id=check.bc_id,
            check_name=check.name,
            check_result=check_result,
            code_block=codeblock,
            file_path=docker_file_path,
            file_line_range=[startline + 1, endline + 1],
            resource=f"{docker_file_path}.{result_instruction}",
            evaluations=None,
            check_class=check.__class__.__module__,
            file_abs_path=file_abs_path,
            entity_tags=None,
            severity=check.severity,
        )
        record.set_guideline(check.guideline)
        report.add_record(record=record)


def get_files_definitions(
    files: list[str], filepath_fn: Callable[[str], str] | None = None
) -> tuple[dict[str, DictNode], dict[str, list[str]]]:
    def _parse_file(file: str) -> tuple[str, tuple[dict[str, list[dict[str, int | str]]], list[str]] | None]:
        try:
            return file, parse(file)
        except TypeError:
            logging.info(f'Dockerfile skipping {file} as it is not a valid dockerfile template')
            return file, None
        except UnicodeDecodeError:
            logging.info(f'Dockerfile skipping {file} as it can\'t be read as text file')
            return file, None

    results = parallel_runner.run_function(_parse_file, files)
    definitions = {}
    definitions_raw = {}
    for file, result in results:
        if result:
            path = filepath_fn(file) if filepath_fn else file
            definitions[path], definitions_raw[path] = result

    return definitions, definitions_raw
