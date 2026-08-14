import textwrap
from pathlib import Path
from typing import Any

from .base import ExecutorError, PreparedProgram
from .compiled import CompiledExecutor
from .typed import cpp_type, encode_case, function_signature


class CppExecutor(CompiledExecutor):
    language = "cpp"
    address_space_overhead_mb = 0
    max_processes = 16
    compiler_path = "/usr/bin/g++"
    benchmark_command = ("/runner/benchmarks/cpp",)
    reference_benchmark_ms = 18.0

    def prepare(
        self,
        job_root: Path,
        scratch: Path,
        code: str,
        invocation: dict[str, Any],
        limits: dict[str, Any],
    ) -> PreparedProgram:
        parameters, _, method = function_signature(invocation, self.language)
        class_name = invocation.get("class_name", "Solution")
        if not isinstance(class_name, str) or not class_name.isidentifier():
            raise ExecutorError("Invalid C++ entry class")
        declarations = "\n".join(
            f"        auto openoj_arg_{index} = OpenOJDecoder<{cpp_type(spec)}>::read(openoj_reader);"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openoj_arg_{index}" for index in range(len(parameters)))
        wrapper = textwrap.dedent(
            f"""
            #undef main
            #undef int

            class OpenOJReader {{
            public:
                explicit OpenOJReader(std::vector<unsigned char> bytes) : data(std::move(bytes)) {{}}
                uint32_t u32() {{
                    require(4);
                    uint32_t value = 0;
                    for (int i = 0; i < 4; ++i) value = (value << 8) | data[offset++];
                    return value;
                }}
                uint64_t u64() {{
                    require(8);
                    uint64_t value = 0;
                    for (int i = 0; i < 8; ++i) value = (value << 8) | data[offset++];
                    return value;
                }}
                unsigned char byte() {{ require(1); return data[offset++]; }}
                std::string text() {{
                    uint32_t length = u32();
                    require(length);
                    std::string value(data.begin() + offset, data.begin() + offset + length);
                    offset += length;
                    return value;
                }}
                void finished() const {{
                    if (offset != data.size()) throw std::runtime_error("Trailing judge input");
                }}
            private:
                std::vector<unsigned char> data;
                size_t offset = 0;
                void require(size_t count) const {{
                    if (count > data.size() - offset) throw std::runtime_error("Truncated judge input");
                }}
            }};

            template <typename T> struct OpenOJDecoder;
            template <> struct OpenOJDecoder<int> {{
                static int read(OpenOJReader& reader) {{ return static_cast<int32_t>(reader.u32()); }}
            }};
            template <> struct OpenOJDecoder<long long> {{
                static long long read(OpenOJReader& reader) {{ return static_cast<int64_t>(reader.u64()); }}
            }};
            template <> struct OpenOJDecoder<double> {{
                static double read(OpenOJReader& reader) {{
                    uint64_t bits = reader.u64();
                    double value;
                    std::memcpy(&value, &bits, sizeof(value));
                    return value;
                }}
            }};
            template <> struct OpenOJDecoder<bool> {{
                static bool read(OpenOJReader& reader) {{
                    auto value = reader.byte();
                    if (value > 1) throw std::runtime_error("Invalid boolean input");
                    return value == 1;
                }}
            }};
            template <> struct OpenOJDecoder<std::string> {{
                static std::string read(OpenOJReader& reader) {{ return reader.text(); }}
            }};
            template <typename T> struct OpenOJDecoder<std::vector<T>> {{
                static std::vector<T> read(OpenOJReader& reader) {{
                    uint32_t length = reader.u32();
                    std::vector<T> values;
                    values.reserve(length);
                    for (uint32_t index = 0; index < length; ++index) {{
                        values.push_back(OpenOJDecoder<T>::read(reader));
                    }}
                    return values;
                }}
            }};

            static std::string openoj_json(const std::string& value) {{
                static const char* hex = "0123456789abcdef";
                std::string output = "\\\"";
                for (unsigned char character : value) {{
                    switch (character) {{
                        case '\\"': output += "\\\\\\\""; break;
                        case '\\\\': output += "\\\\\\\\"; break;
                        case '\\b': output += "\\\\b"; break;
                        case '\\f': output += "\\\\f"; break;
                        case '\\n': output += "\\\\n"; break;
                        case '\\r': output += "\\\\r"; break;
                        case '\\t': output += "\\\\t"; break;
                        default:
                            if (character < 0x20) {{
                                output += "\\\\u00";
                                output += hex[character >> 4];
                                output += hex[character & 15];
                            }} else output += static_cast<char>(character);
                    }}
                }}
                return output + "\\\"";
            }}
            static std::string openoj_json(bool value) {{ return value ? "true" : "false"; }}
            static std::string openoj_json(int value) {{ return std::to_string(value); }}
            static std::string openoj_json(long long value) {{ return std::to_string(value); }}
            static std::string openoj_json(double value) {{
                if (!std::isfinite(value)) throw std::runtime_error("Non-finite return value");
                std::ostringstream output;
                output << std::setprecision(17) << value;
                return output.str();
            }}
            template <typename T> static std::string openoj_json(const std::vector<T>& values) {{
                std::string output = "[";
                for (size_t index = 0; index < values.size(); ++index) {{
                    if (index) output += ',';
                    output += openoj_json(values[index]);
                }}
                return output + "]";
            }}

            int main() {{
                try {{
                    std::vector<unsigned char> bytes(
                        std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()
                    );
                    OpenOJReader openoj_reader(std::move(bytes));
            {declarations}
                    openoj_reader.finished();
                    {class_name} openoj_solution;
                    auto openoj_actual = openoj_solution.{method}({arguments});
                    std::cout << "__OPENOJ_RESULT__{{\\\"status\\\":\\\"completed\\\",\\\"actual\\\":"
                              << openoj_json(openoj_actual) << "}}\\n";
                }} catch (const std::exception& error) {{
                    std::cout << "__OPENOJ_RESULT__{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":"
                              << openoj_json(std::string(error.what())) << "}}\\n";
                }} catch (...) {{
                    std::cout << "__OPENOJ_RESULT__{{\\\"status\\\":\\\"runtime_error\\\","
                                 "\\\"error\\\":\\\"Unknown C++ exception\\\"}}\\n";
                }}
                return 0;
            }}
            """
        )
        source_path = job_root / "main.cpp"
        executable = job_root / "solution"
        source_path.write_text(
            "#include <bits/stdc++.h>\nusing namespace std;\n" + code + "\n" + wrapper,
            encoding="utf-8",
        )
        source_path.chmod(0o444)
        self.compile(
            job_root,
            (
                self.compiler_path,
                "-std=c++20",
                "-O2",
                "-pipe",
                "-fno-diagnostics-color",
                "-o",
                str(executable),
                str(source_path),
            ),
            executable,
            {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"},
        )
        return PreparedProgram(
            command=(str(executable),),
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        return encode_case(invocation, case_input, self.language)
