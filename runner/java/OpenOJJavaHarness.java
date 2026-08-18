import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class OpenOJJavaHarness {
    private static final String PROTOCOL_PREFIX = "__OPENOJ_RESULT__";
    private static final int MAX_CAPTURED_OUTPUT = 16_384;
    private static final long SCHEDULE_STACK_BYTES = 512L * 1024L;

    private OpenOJJavaHarness() {}

    public static void main(String[] arguments) {
        if (arguments.length == 1 && "--benchmark".equals(arguments[0])) {
            benchmark();
            return;
        }

        PrintStream protocolOutput = openProtocolChannel();
        CappedOutputStream capturedBytes = new CappedOutputStream(MAX_CAPTURED_OUTPUT);
        PrintStream capturedOutput = new PrintStream(capturedBytes, true, StandardCharsets.UTF_8);
        Map<String, Object> response = new LinkedHashMap<>();
        try {
            String payloadText = new String(System.in.readAllBytes(), StandardCharsets.UTF_8);
            Object parsed = Json.parse(payloadText);
            Map<String, Object> payload = asMap(parsed, "Judge payload must be an object");
            Map<String, Object> invocation = asMap(payload.get("invocation"), "Invocation must be an object");

            System.setOut(capturedOutput);
            Object actual = invoke(invocation, payload.get("input"));
            response.put("status", "completed");
            response.put("actual", actual);
        } catch (Throwable error) {
            Throwable root = unwrap(error);
            response.put("status", "runtime_error");
            response.put("error", boundedError(root));
        } finally {
            System.setOut(protocolOutput);
            capturedOutput.flush();
            response.put("stdout", capturedBytes.asString());
        }

        try {
            protocolOutput.println(PROTOCOL_PREFIX + Json.stringify(response));
        } catch (Throwable serializationError) {
            Map<String, Object> fallback = new LinkedHashMap<>();
            fallback.put("status", "runtime_error");
            fallback.put("error", boundedError(unwrap(serializationError)));
            fallback.put("stdout", capturedBytes.asString());
            protocolOutput.println(PROTOCOL_PREFIX + Json.stringify(fallback));
        }
    }

    /**
     * The judge protocol prefers a dedicated inherited fd (63) so submission
     * code cannot forge verdicts on stdout; stdout is the fallback when the
     * fd is absent (local authoring tooling).
     */
    private static PrintStream openProtocolChannel() {
        try {
            java.io.FileOutputStream channel = new java.io.FileOutputStream("/dev/fd/63");
            return new PrintStream(channel, true, StandardCharsets.UTF_8);
        } catch (Throwable unavailable) {
            return System.out;
        }
    }

    private static void benchmark() {
        long accumulator = 0x12345678L;
        for (int value = 0; value < 3_000_000; value++) {
            accumulator = ((accumulator << 5) - accumulator + value) & 0xffffffffL;
        }
        if (accumulator == -1L) {
            throw new IllegalStateException("Unreachable benchmark state");
        }
        System.out.print(accumulator);
    }

    private static Object invoke(Map<String, Object> invocation, Object rawInput) throws Exception {
        String className = asString(invocation.get("class_name"), "Invocation class_name must be a string");
        Class<?> targetClass = Class.forName(className);
        String type = invocation.getOrDefault("type", "function").toString();
        if ("design".equals(type)) {
            return invokeDesign(targetClass, invocation, rawInput);
        }
        if ("interactive".equals(type)) {
            return invokeInteractive(targetClass, invocation, rawInput);
        }
        if ("concurrent".equals(type)) {
            return invokeConcurrent(targetClass, invocation, rawInput);
        }
        if (!"function".equals(type)) {
            throw new IllegalArgumentException("Unsupported invocation type: " + type);
        }
        return invokeFunction(targetClass, invocation, rawInput);
    }

    /** Builds the oracle named by the invocation from the case state. */
    private static Object buildOracle(String oracle, Map<String, Object> state, long budget) {
        switch (oracle) {
            case "GridMaster": {
                List<Object> grid = asList(state.get("grid"), "Interactive grid must be a list");
                List<Object> start = asList(state.get("start"), "Interactive start must be [row, col]");
                List<Object> target = asList(state.get("target"), "Interactive target must be [row, col]");
                return new GridMaster(
                    grid,
                    numberValue(start.get(0)).intValue(),
                    numberValue(start.get(1)).intValue(),
                    numberValue(target.get(0)).intValue(),
                    numberValue(target.get(1)).intValue(),
                    budget
                );
            }
            case "Robot": {
                List<Object> room = asList(state.get("room"), "Robot room must be a list");
                List<Object> start = asList(state.get("start"), "Robot start must be [row, col]");
                return new InteractiveOracles.Robot(
                    room,
                    numberValue(start.get(0)).intValue(),
                    numberValue(start.get(1)).intValue(),
                    budget
                );
            }
            case "Master":
                return new InteractiveOracles.Master(
                    asList(state.get("wordlist"), "Master wordlist must be a list"),
                    asString(state.get("secret"), "Master secret must be a string"),
                    budget
                );
            case "MountainArray":
                return new InteractiveOracles.MountainArray(
                    asList(state.get("mountain"), "MountainArray values must be a list"),
                    budget
                );
            case "BinaryMatrix":
                return new InteractiveOracles.BinaryMatrix(
                    asList(state.get("matrix"), "BinaryMatrix rows must be a list"),
                    budget
                );
            case "ArrayReader":
                return new InteractiveOracles.ArrayReader(
                    asList(state.get("arr"), "ArrayReader values must be a list"),
                    budget
                );
            case "InfiniteStream":
                return new InteractiveOracles.InfiniteStream(
                    asList(state.get("bits"), "InfiniteStream bits must be a list"),
                    budget
                );
            case "Sea":
                return new InteractiveOracles.Sea(
                    asList(state.get("ships"), "Sea ships must be a list"),
                    budget
                );
            default:
                throw new IllegalArgumentException("Unsupported interactive oracle: " + oracle);
        }
    }

    /**
     * Some oracles pair with auxiliary case data the solution method also
     * needs — LeetCode's two-argument signatures (guess-the-word's wordlist,
     * mountain-array's target, ...). The case key listed here is converted
     * and passed to the method as a second argument, after the oracle.
     */
    private static Object[] auxiliaryArguments(String oracle, Map<String, Object> state) {
        switch (oracle) {
            case "Master":
                return new Object[] {
                    convert(
                        asList(state.get("wordlist"), "Master wordlist must be a list"),
                        String[].class,
                        String[].class
                    ),
                };
            case "MountainArray":
            case "ArrayReader":
                return new Object[] { numberValue(state.get("target")).intValue() };
            case "InfiniteStream":
                return new Object[] {
                    convert(
                        asList(state.get("pattern"), "InfiniteStream pattern must be a list"),
                        int[].class,
                        int[].class
                    ),
                };
            case "Sea":
                // countShips takes the search box alongside the oracle.
                return new Object[] {
                    convert(asList(state.get("topRight"), "Sea topRight must be a list"), int[].class, int[].class),
                    convert(asList(state.get("bottomLeft"), "Sea bottomLeft must be a list"), int[].class, int[].class),
                };
            default:
                return new Object[0];
        }
    }

    /**
     * Runs a schedule of calls on real threads and reports what happened.
     * Each schedule entry becomes one thread; a call that LeetCode hands a
     * Runnable declares `emits` and receives a callback appending that token
     * to the shared log, while a call declaring `records` contributes its
     * return value when it completes. The judge compares the log against the
     * problem's invariant, because a correct concurrent program has many
     * valid interleavings.
     */
    private static Object invokeConcurrent(
        Class<?> targetClass,
        Map<String, Object> invocation,
        Object rawInput
    ) throws Exception {
        Map<String, Object> state = asMap(rawInput, "Concurrent input must be an object");
        List<Object> schedule = asList(state.get("threads"), "Concurrent input needs a threads list");
        if (schedule.isEmpty()) {
            throw new IllegalArgumentException("Concurrent schedule must not be empty");
        }
        List<Object> constructorArguments = state.get("constructor") == null
            ? new ArrayList<>()
            : asList(state.get("constructor"), "Constructor params must be a list");
        InvocationPlan<Constructor<?>> constructorPlan = findConstructor(targetClass, constructorArguments);
        Object instance;
        try {
            instance = constructorPlan.executable().newInstance(constructorPlan.arguments());
        } catch (InvocationTargetException error) {
            throw propagate(error.getTargetException());
        }

        List<Object> events = java.util.Collections.synchronizedList(new ArrayList<>());
        List<Throwable> failures = java.util.Collections.synchronizedList(new ArrayList<>());
        List<Thread> threads = new ArrayList<>();
        for (Object entry : schedule) {
            Map<String, Object> spec = asMap(entry, "Schedule entry must be an object");
            String call = asString(spec.get("call"), "Schedule entry needs a call name");
            List<Object> arguments = spec.get("args") == null
                ? new ArrayList<>()
                : asList(spec.get("args"), "Schedule args must be a list");
            Object emits = spec.get("emits");
            boolean records = Boolean.TRUE.equals(spec.get("records"));
            threads.add(new Thread(null, () -> {
                try {
                    if (emits != null) {
                        List<Object> callArguments = new ArrayList<>(arguments);
                        callArguments.add((Runnable) () -> events.add(emits));
                        InvocationPlan<Method> plan = findMethod(targetClass, call, callArguments);
                        plan.executable().invoke(instance, plan.arguments());
                    } else {
                        InvocationPlan<Method> plan = findMethod(targetClass, call, arguments);
                        Object value = plan.executable().invoke(instance, plan.arguments());
                        if (records) {
                            events.add(value);
                        }
                    }
                } catch (InvocationTargetException error) {
                    failures.add(error.getTargetException());
                } catch (Throwable error) {
                    failures.add(error);
                }
                // Each thread reserves its stack from the sandbox's
                // address-space allowance; the default times a schedule's
                // worth of threads exceeds it, and a schedule thread runs one
                // short method, so a small stack is ample.
            }, "openoj-schedule", SCHEDULE_STACK_BYTES));
        }
        for (Thread thread : threads) {
            thread.setDaemon(true);
            thread.start();
        }
        // The outer judge timeout is the deadlock detector: a schedule that
        // never completes simply never returns, and the case times out.
        for (Thread thread : threads) {
            thread.join();
        }
        if (!failures.isEmpty()) {
            throw propagate(failures.get(0));
        }
        return new ArrayList<>(events);
    }

    private static Object invokeInteractive(
        Class<?> targetClass,
        Map<String, Object> invocation,
        Object rawInput
    ) throws Exception {
        String oracle = invocation.getOrDefault("oracle", "GridMaster").toString();
        Map<String, Object> state = asMap(rawInput, "Interactive input must be an object");
        long budget = numberValue(invocation.getOrDefault("query_limit", 1_000_000)).longValue();
        Object oracleInstance = buildOracle(oracle, state, budget);
        Object[] auxiliary = auxiliaryArguments(oracle, state);

        Constructor<?> constructor = targetClass.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object instance = constructor.newInstance();
        String method = asString(invocation.get("method"), "Invocation method must be a string");
        for (Method candidate : targetClass.getDeclaredMethods()) {
            if (!candidate.getName().equals(method)) {
                continue;
            }
            candidate.setAccessible(true);
            Object[] callArguments = new Object[1 + auxiliary.length];
            callArguments[0] = oracleInstance;
            System.arraycopy(auxiliary, 0, callArguments, 1, auxiliary.length);
            Object result = candidate.invoke(instance, callArguments);
            // Void-method oracles are judged by their own final state —
            // e.g. the robot's exact set of cleaned cells.
            if (result == null) {
                try {
                    return oracleInstance
                        .getClass()
                        .getMethod("verdict")
                        .invoke(oracleInstance);
                } catch (NoSuchMethodException noVerdict) {
                    return null;
                }
            }
            return result;
        }
        throw new IllegalArgumentException("Method not found on solution class: " + method);
    }

    private static Object invokeFunction(
        Class<?> targetClass,
        Map<String, Object> invocation,
        Object rawInput
    ) throws Exception {
        List<Object> rawArguments = asList(rawInput, "Function input must be a positional argument list");
        List<Object> parameterSpecs = asList(invocation.getOrDefault("parameters", List.of()), "Parameters must be a list");
        if (parameterSpecs.size() != rawArguments.size()) {
            throw new IllegalArgumentException("Input argument count does not match the problem manifest");
        }
        for (int index = 0; index < parameterSpecs.size(); index++) {
            Map<String, Object> spec = asMap(parameterSpecs.get(index), "Parameter spec must be an object");
            String codec = spec.getOrDefault("codec", "json").toString();
            rawArguments.set(index, decodeCodec(rawArguments.get(index), codec));
        }

        Constructor<?> constructor = targetClass.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object instance = constructor.newInstance();
        String methodName = asString(invocation.get("method"), "Invocation method must be a string");
        InvocationPlan<Method> plan = findMethod(targetClass, methodName, rawArguments);
        Object result;
        try {
            result = plan.executable().invoke(instance, plan.arguments());
        } catch (InvocationTargetException error) {
            throw propagate(error.getTargetException());
        }
        return encodeCodec(result, invocation.getOrDefault("return_codec", "json").toString());
    }

    private static Object decodeCodec(Object value, String codec) {
        if ("json".equals(codec)) {
            return value;
        }
        if ("list_node".equals(codec)) {
            if (value == null) {
                return null;
            }
            List<Object> values = asList(value, "list_node input must be an array");
            ListNode head = null;
            ListNode current = null;
            for (Object item : values) {
                ListNode node = new ListNode(numberValue(item).intValue());
                if (current == null) {
                    head = node;
                } else {
                    current.next = node;
                }
                current = node;
            }
            return head;
        }
        if ("tree_node".equals(codec)) {
            if (value == null) {
                return null;
            }
            List<Object> values = asList(value, "tree_node input must be a level-order array");
            if (values.isEmpty() || values.get(0) == null) {
                return null;
            }
            TreeNode root = new TreeNode(numberValue(values.get(0)).intValue());
            // Null children are skipped below, so a growable list doubles as the BFS queue.
            List<Object> pending = new ArrayList<>();
            pending.add(root);
            int readIndex = 1;
            int writeIndex = 0;
            while (writeIndex < pending.size() && readIndex < values.size()) {
                Object entry = pending.get(writeIndex++);
                if (!(entry instanceof TreeNode node)) {
                    continue;
                }
                if (readIndex < values.size()) {
                    if (values.get(readIndex) != null) {
                        node.left = new TreeNode(numberValue(values.get(readIndex)).intValue());
                        pending.add(node.left);
                    }
                    readIndex++;
                }
                if (readIndex < values.size()) {
                    if (values.get(readIndex) != null) {
                        node.right = new TreeNode(numberValue(values.get(readIndex)).intValue());
                        pending.add(node.right);
                    }
                    readIndex++;
                }
            }
            return root;
        }
        if ("list_node_array".equals(codec) || "tree_node_array".equals(codec)) {
            List<Object> values = asList(value, codec + " input must be an array");
            List<Object> nodes = new ArrayList<>();
            for (Object item : values) {
                nodes.add(decodeCodec(item, codec.substring(0, codec.length() - 6)));
            }
            return nodes;
        }
        throw new IllegalArgumentException("Java executor does not support codec: " + codec);
    }

    private static Object encodeCodec(Object value, String codec) {
        if ("json".equals(codec)) {
            return value;
        }
        if (value == null) {
            // Every other executor serializes a missing head or root as [].
            return List.of();
        }
        if ("list_node".equals(codec)) {
            if (!(value instanceof ListNode node)) {
                throw new IllegalArgumentException("list_node return value must be a ListNode");
            }
            List<Object> values = new ArrayList<>();
            for (ListNode current = node; current != null; current = current.next) {
                values.add(current.val);
            }
            return values;
        }
        if ("tree_node".equals(codec)) {
            if (!(value instanceof TreeNode root)) {
                throw new IllegalArgumentException("tree_node return value must be a TreeNode");
            }
            List<Object> values = new ArrayList<>();
            List<Object> queue = new ArrayList<>();
            queue.add(root);
            int index = 0;
            while (index < queue.size()) {
                Object entry = queue.get(index++);
                if (entry == null) {
                    values.add(null);
                    continue;
                }
                TreeNode node = (TreeNode) entry;
                values.add(node.val);
                queue.add(node.left);
                queue.add(node.right);
            }
            while (!values.isEmpty() && values.get(values.size() - 1) == null) {
                values.remove(values.size() - 1);
            }
            return values;
        }
        if ("list_node_array".equals(codec) || "tree_node_array".equals(codec)) {
            List<?> items = asList(value, codec + " return value must be an array");
            List<Object> values = new ArrayList<>();
            for (Object item : items) {
                values.add(encodeCodec(item, codec.substring(0, codec.length() - 6)));
            }
            return values;
        }
        throw new IllegalArgumentException("Java executor does not support codec: " + codec);
    }

    private static Number numberValue(Object value) {
        if (value instanceof Number number) {
            return number;
        }
        throw new IllegalArgumentException("Expected a JSON number but found: " + value);
    }

    /** Per-method (parameter codecs, return codec) from the manifest. */
    private static Map<String, Object[]> methodCodecs(Map<String, Object> invocation) {
        Map<String, Object[]> table = new LinkedHashMap<>();
        Object declared = invocation.get("methods");
        if (!(declared instanceof List<?> methods)) {
            return table;
        }
        for (Object entry : methods) {
            if (!(entry instanceof Map<?, ?> method)) {
                continue;
            }
            List<String> parameterCodecs = new ArrayList<>();
            if (method.get("parameters") instanceof List<?> parameters) {
                for (Object parameter : parameters) {
                    String codec = "json";
                    if (parameter instanceof Map<?, ?> spec && spec.get("codec") != null) {
                        codec = spec.get("codec").toString();
                    }
                    parameterCodecs.add(codec);
                }
            }
            Object returnCodec = method.get("return_codec");
            table.put(
                asString(method.get("name"), "Method name must be a string"),
                new Object[] { parameterCodecs, returnCodec == null ? "json" : returnCodec.toString() }
            );
        }
        return table;
    }

    private static Object invokeDesign(
        Class<?> targetClass,
        Map<String, Object> invocation,
        Object rawInput
    ) throws Exception {
        Map<String, Object> designInput = asMap(rawInput, "Design input must be an object");
        List<Object> actions = asList(designInput.get("actions"), "Design actions must be a list");
        List<Object> params = asList(designInput.get("params"), "Design params must be a list");
        if (actions.isEmpty() || actions.size() != params.size()) {
            throw new IllegalArgumentException("Design actions and params must have the same non-zero length");
        }
        List<Object> constructorArguments = asList(params.get(0), "Constructor params must be a list");
        if (invocation.get("constructor") instanceof Map<?, ?> constructorSpec
            && constructorSpec.get("parameters") instanceof List<?> constructorParameters) {
            for (int slot = 0; slot < constructorArguments.size() && slot < constructorParameters.size(); slot++) {
                String codec = "json";
                if (constructorParameters.get(slot) instanceof Map<?, ?> spec && spec.get("codec") != null) {
                    codec = spec.get("codec").toString();
                }
                constructorArguments.set(slot, decodeCodec(constructorArguments.get(slot), codec));
            }
        }
        InvocationPlan<Constructor<?>> constructorPlan = findConstructor(targetClass, constructorArguments);
        Object instance;
        try {
            instance = constructorPlan.executable().newInstance(constructorPlan.arguments());
        } catch (InvocationTargetException error) {
            throw propagate(error.getTargetException());
        }

        Map<String, Object[]> codecs = methodCodecs(invocation);
        List<Object> output = new ArrayList<>();
        output.add(null);
        // Raw (undecoded, unencoded) returns feed piped arguments, so a piped
        // value crosses methods as the live object rather than its wire form.
        List<Object> rawOutput = new ArrayList<>();
        rawOutput.add(null);
        for (int index = 1; index < actions.size(); index++) {
            String methodName;
            int repeat = 1;
            // A repeated action ({"call": name, "repeat": K}) is a randomized
            // method under statistical judging: invoke K times, report the
            // frequency table keyed by the canonical JSON of each value.
            if (actions.get(index) instanceof Map<?, ?> actionMap) {
                methodName = asString(actionMap.get("call"), "Repeated action needs a call name");
                Object repeatSpec = actionMap.get("repeat");
                if (repeatSpec != null) {
                    repeat = numberValue(repeatSpec).intValue();
                }
            } else {
                methodName = asString(actions.get(index), "Design action must be a string");
            }
            Object[] methodCodec = codecs.getOrDefault(methodName, new Object[] { List.of(), "json" });
            @SuppressWarnings("unchecked")
            List<String> parameterCodecs = (List<String>) methodCodec[0];
            String returnCodec = methodCodec[1].toString();
            List<Object> methodArguments = asList(params.get(index), "Method params must be a list");
            for (int slot = 0; slot < methodArguments.size(); slot++) {
                Object argument = methodArguments.get(slot);
                // {"$prev": i} feeds action i's own return value straight back
                // in, so a round-trip pair is judged without pinning the
                // intermediate format.
                if (argument instanceof Map<?, ?> pipe && pipe.size() == 1 && pipe.get("$prev") != null) {
                    methodArguments.set(slot, rawOutput.get(numberValue(pipe.get("$prev")).intValue()));
                } else if (slot < parameterCodecs.size()) {
                    methodArguments.set(slot, decodeCodec(argument, parameterCodecs.get(slot)));
                }
            }
            InvocationPlan<Method> methodPlan = findMethod(targetClass, methodName, methodArguments);
            if (repeat <= 1) {
                Object value;
                try {
                    value = methodPlan.executable().invoke(instance, methodPlan.arguments());
                } catch (InvocationTargetException error) {
                    throw propagate(error.getTargetException());
                }
                rawOutput.add(value);
                output.add(encodeCodec(value, returnCodec));
                continue;
            }
            Map<String, Integer> counts = new LinkedHashMap<>();
            Object last = null;
            for (int draw = 0; draw < repeat; draw++) {
                try {
                    last = methodPlan.executable().invoke(instance, methodPlan.arguments());
                } catch (InvocationTargetException error) {
                    throw propagate(error.getTargetException());
                }
                String key = Json.stringify(encodeCodec(last, returnCodec));
                counts.merge(key, 1, Integer::sum);
            }
            rawOutput.add(last);
            output.add(counts);
        }
        return output;
    }

    private static InvocationPlan<Method> findMethod(
        Class<?> targetClass,
        String name,
        List<Object> rawArguments
    ) {
        IllegalArgumentException lastConversionError = null;
        for (Method method : targetClass.getDeclaredMethods()) {
            if (!method.getName().equals(name) || method.getParameterCount() != rawArguments.size()) {
                continue;
            }
            try {
                method.setAccessible(true);
                return new InvocationPlan<>(method, convertArguments(method, rawArguments));
            } catch (IllegalArgumentException error) {
                lastConversionError = error;
            }
        }
        if (lastConversionError != null) {
            throw lastConversionError;
        }
        throw new IllegalArgumentException("No matching method " + name + " with " + rawArguments.size() + " arguments");
    }

    private static InvocationPlan<Constructor<?>> findConstructor(
        Class<?> targetClass,
        List<Object> rawArguments
    ) {
        IllegalArgumentException lastConversionError = null;
        for (Constructor<?> constructor : targetClass.getDeclaredConstructors()) {
            if (constructor.getParameterCount() != rawArguments.size()) {
                continue;
            }
            try {
                constructor.setAccessible(true);
                return new InvocationPlan<>(constructor, convertArguments(constructor, rawArguments));
            } catch (IllegalArgumentException error) {
                lastConversionError = error;
            }
        }
        if (lastConversionError != null) {
            throw lastConversionError;
        }
        throw new IllegalArgumentException("No matching constructor with " + rawArguments.size() + " arguments");
    }

    private static Object[] convertArguments(Executable executable, List<Object> rawArguments) {
        Class<?>[] parameterTypes = executable.getParameterTypes();
        Type[] genericTypes = executable.getGenericParameterTypes();
        Object[] converted = new Object[rawArguments.size()];
        for (int index = 0; index < rawArguments.size(); index++) {
            converted[index] = convert(rawArguments.get(index), parameterTypes[index], genericTypes[index]);
        }
        return converted;
    }

    private static Object convert(Object value, Class<?> targetType, Type genericType) {
        if (value == null) {
            if (targetType.isPrimitive()) {
                throw new IllegalArgumentException("null cannot be converted to " + targetType.getName());
            }
            return null;
        }
        if (targetType == Object.class || targetType.isInstance(value)) {
            return value;
        }
        if (targetType == String.class) {
            if (!(value instanceof String)) throw conversionError(value, targetType);
            return value;
        }
        if (targetType == char.class || targetType == Character.class) {
            if (value instanceof String text && text.length() == 1) return text.charAt(0);
            throw conversionError(value, targetType);
        }
        if (targetType == boolean.class || targetType == Boolean.class) {
            if (value instanceof Boolean) return value;
            throw conversionError(value, targetType);
        }
        if (value instanceof Number number) {
            if (targetType == byte.class || targetType == Byte.class) return number.byteValue();
            if (targetType == short.class || targetType == Short.class) return number.shortValue();
            if (targetType == int.class || targetType == Integer.class) return Math.toIntExact(number.longValue());
            if (targetType == long.class || targetType == Long.class) return number.longValue();
            if (targetType == float.class || targetType == Float.class) return number.floatValue();
            if (targetType == double.class || targetType == Double.class) return number.doubleValue();
        }
        if (targetType.isArray()) {
            List<Object> values = asList(value, "Array argument must be a JSON array");
            Class<?> componentType = targetType.getComponentType();
            Object array = Array.newInstance(componentType, values.size());
            for (int index = 0; index < values.size(); index++) {
                Array.set(array, index, convert(values.get(index), componentType, componentType));
            }
            return array;
        }
        if (Collection.class.isAssignableFrom(targetType)) {
            List<Object> values = asList(value, "Collection argument must be a JSON array");
            Collection<Object> collection = Set.class.isAssignableFrom(targetType)
                ? new LinkedHashSet<>()
                : new ArrayList<>();
            Type elementType = Object.class;
            if (genericType instanceof ParameterizedType parameterized) {
                elementType = parameterized.getActualTypeArguments()[0];
            }
            Class<?> elementClass = rawClass(elementType);
            for (Object item : values) {
                collection.add(convert(item, elementClass, elementType));
            }
            return collection;
        }
        if (Map.class.isAssignableFrom(targetType)) {
            Map<String, Object> values = asMap(value, "Map argument must be a JSON object");
            return new LinkedHashMap<>(values);
        }
        if (targetType.isEnum() && value instanceof String text) {
            @SuppressWarnings({"unchecked", "rawtypes"})
            Object constant = Enum.valueOf((Class<? extends Enum>) targetType, text);
            return constant;
        }
        throw conversionError(value, targetType);
    }

    private static Class<?> rawClass(Type type) {
        if (type instanceof Class<?> clazz) return clazz;
        if (type instanceof ParameterizedType parameterized && parameterized.getRawType() instanceof Class<?> clazz) {
            return clazz;
        }
        return Object.class;
    }

    private static IllegalArgumentException conversionError(Object value, Class<?> targetType) {
        return new IllegalArgumentException("Cannot convert " + value.getClass().getSimpleName() + " to " + targetType.getTypeName());
    }

    private static RuntimeException propagate(Throwable error) {
        if (error instanceof RuntimeException runtime) return runtime;
        if (error instanceof Error serious) throw serious;
        return new RuntimeException(error);
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while (current instanceof InvocationTargetException invocation && invocation.getTargetException() != null) {
            current = invocation.getTargetException();
        }
        return current;
    }

    private static String boundedError(Throwable error) {
        String message = error.getMessage();
        String text = error.getClass().getSimpleName() + (message == null || message.isBlank() ? "" : ": " + message);
        return text.length() <= 4096 ? text : text.substring(0, 4096);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value, String message) {
        if (!(value instanceof Map<?, ?> map)) throw new IllegalArgumentException(message);
        return (Map<String, Object>) map;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> asList(Object value, String message) {
        if (!(value instanceof List<?> list)) throw new IllegalArgumentException(message);
        return (List<Object>) list;
    }

    private static String asString(Object value, String message) {
        if (!(value instanceof String text)) throw new IllegalArgumentException(message);
        return text;
    }

    private record InvocationPlan<T extends Executable>(T executable, Object[] arguments) {}

    private static final class CappedOutputStream extends OutputStream {
        private final ByteArrayOutputStream delegate = new ByteArrayOutputStream();
        private final int limit;

        private CappedOutputStream(int limit) {
            this.limit = limit;
        }

        @Override
        public void write(int value) {
            if (delegate.size() < limit) delegate.write(value);
        }

        @Override
        public void write(byte[] bytes, int offset, int length) {
            int remaining = limit - delegate.size();
            if (remaining > 0) delegate.write(bytes, offset, Math.min(length, remaining));
        }

        private String asString() {
            return delegate.toString(StandardCharsets.UTF_8);
        }
    }

    private static final class Json {
        private Json() {}

        static Object parse(String text) {
            Parser parser = new Parser(text);
            Object value = parser.parseValue();
            parser.skipWhitespace();
            if (!parser.atEnd()) throw new IllegalArgumentException("Unexpected trailing JSON data");
            return value;
        }

        static String stringify(Object value) {
            StringBuilder output = new StringBuilder();
            writeValue(output, value);
            return output.toString();
        }

        private static void writeValue(StringBuilder output, Object value) {
            if (value == null) {
                output.append("null");
            } else if (value instanceof String text) {
                writeString(output, text);
            } else if (value instanceof Character character) {
                writeString(output, character.toString());
            } else if (value instanceof Boolean || value instanceof Byte || value instanceof Short
                || value instanceof Integer || value instanceof Long) {
                output.append(value);
            } else if (value instanceof Float number) {
                if (!Float.isFinite(number)) throw new IllegalArgumentException("Non-finite number cannot be serialized");
                output.append(number);
            } else if (value instanceof Double number) {
                if (!Double.isFinite(number)) throw new IllegalArgumentException("Non-finite number cannot be serialized");
                output.append(number);
            } else if (value.getClass().isArray()) {
                output.append('[');
                for (int index = 0; index < Array.getLength(value); index++) {
                    if (index > 0) output.append(',');
                    writeValue(output, Array.get(value, index));
                }
                output.append(']');
            } else if (value instanceof Iterable<?> items) {
                output.append('[');
                boolean first = true;
                for (Object item : items) {
                    if (!first) output.append(',');
                    first = false;
                    writeValue(output, item);
                }
                output.append(']');
            } else if (value instanceof Map<?, ?> map) {
                output.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!(entry.getKey() instanceof String key)) {
                        throw new IllegalArgumentException("JSON object keys must be strings");
                    }
                    if (!first) output.append(',');
                    first = false;
                    writeString(output, key);
                    output.append(':');
                    writeValue(output, entry.getValue());
                }
                output.append('}');
            } else {
                throw new IllegalArgumentException("Unsupported return type: " + value.getClass().getTypeName());
            }
        }

        private static void writeString(StringBuilder output, String text) {
            output.append('"');
            for (int index = 0; index < text.length(); index++) {
                char character = text.charAt(index);
                switch (character) {
                    case '"' -> output.append("\\\"");
                    case '\\' -> output.append("\\\\");
                    case '\b' -> output.append("\\b");
                    case '\f' -> output.append("\\f");
                    case '\n' -> output.append("\\n");
                    case '\r' -> output.append("\\r");
                    case '\t' -> output.append("\\t");
                    default -> {
                        if (character < 0x20) output.append(String.format("\\u%04x", (int) character));
                        else output.append(character);
                    }
                }
            }
            output.append('"');
        }

        private static final class Parser {
            private final String text;
            private int position;

            private Parser(String text) {
                this.text = text;
            }

            private Object parseValue() {
                skipWhitespace();
                if (atEnd()) throw error("Unexpected end of JSON");
                return switch (text.charAt(position)) {
                    case 'n' -> parseLiteral("null", null);
                    case 't' -> parseLiteral("true", true);
                    case 'f' -> parseLiteral("false", false);
                    case '"' -> parseString();
                    case '[' -> parseArray();
                    case '{' -> parseObject();
                    default -> parseNumber();
                };
            }

            private Object parseLiteral(String literal, Object value) {
                if (!text.startsWith(literal, position)) throw error("Invalid JSON literal");
                position += literal.length();
                return value;
            }

            private List<Object> parseArray() {
                position++;
                List<Object> values = new ArrayList<>();
                skipWhitespace();
                if (consume(']')) return values;
                while (true) {
                    values.add(parseValue());
                    skipWhitespace();
                    if (consume(']')) return values;
                    require(',');
                }
            }

            private Map<String, Object> parseObject() {
                position++;
                Map<String, Object> values = new LinkedHashMap<>();
                skipWhitespace();
                if (consume('}')) return values;
                while (true) {
                    skipWhitespace();
                    if (atEnd() || text.charAt(position) != '"') throw error("JSON object key must be a string");
                    String key = parseString();
                    skipWhitespace();
                    require(':');
                    values.put(key, parseValue());
                    skipWhitespace();
                    if (consume('}')) return values;
                    require(',');
                }
            }

            private String parseString() {
                require('"');
                StringBuilder value = new StringBuilder();
                while (!atEnd()) {
                    char character = text.charAt(position++);
                    if (character == '"') return value.toString();
                    if (character != '\\') {
                        if (character < 0x20) throw error("Control character in JSON string");
                        value.append(character);
                        continue;
                    }
                    if (atEnd()) throw error("Unterminated JSON escape");
                    char escape = text.charAt(position++);
                    switch (escape) {
                        case '"', '\\', '/' -> value.append(escape);
                        case 'b' -> value.append('\b');
                        case 'f' -> value.append('\f');
                        case 'n' -> value.append('\n');
                        case 'r' -> value.append('\r');
                        case 't' -> value.append('\t');
                        case 'u' -> value.append(parseUnicode());
                        default -> throw error("Invalid JSON escape");
                    }
                }
                throw error("Unterminated JSON string");
            }

            private char parseUnicode() {
                if (position + 4 > text.length()) throw error("Incomplete Unicode escape");
                try {
                    int codePoint = Integer.parseInt(text.substring(position, position + 4), 16);
                    position += 4;
                    return (char) codePoint;
                } catch (NumberFormatException invalidNumber) {
                    throw error("Invalid Unicode escape");
                }
            }

            private Number parseNumber() {
                int start = position;
                if (consume('-')) {}
                if (consume('0')) {
                    // A single leading zero is valid; further digits are rejected below.
                } else {
                    requireDigit();
                    while (!atEnd() && Character.isDigit(text.charAt(position))) position++;
                }
                boolean decimal = false;
                if (consume('.')) {
                    decimal = true;
                    requireDigit();
                    while (!atEnd() && Character.isDigit(text.charAt(position))) position++;
                }
                if (!atEnd() && (text.charAt(position) == 'e' || text.charAt(position) == 'E')) {
                    decimal = true;
                    position++;
                    if (!atEnd() && (text.charAt(position) == '+' || text.charAt(position) == '-')) position++;
                    requireDigit();
                    while (!atEnd() && Character.isDigit(text.charAt(position))) position++;
                }
                String token = text.substring(start, position);
                try {
                    return decimal ? Double.parseDouble(token) : Long.parseLong(token);
                } catch (NumberFormatException invalidNumber) {
                    throw error("Invalid JSON number");
                }
            }

            private void requireDigit() {
                if (atEnd() || !Character.isDigit(text.charAt(position))) throw error("Expected a digit");
                position++;
            }

            private void require(char expected) {
                skipWhitespace();
                if (!consume(expected)) throw error("Expected '" + expected + "'");
            }

            private boolean consume(char expected) {
                if (!atEnd() && text.charAt(position) == expected) {
                    position++;
                    return true;
                }
                return false;
            }

            private void skipWhitespace() {
                while (!atEnd() && Character.isWhitespace(text.charAt(position))) position++;
            }

            private boolean atEnd() {
                return position >= text.length();
            }

            private IllegalArgumentException error(String message) {
                return new IllegalArgumentException(message + " at character " + position);
            }
        }
    }
}
