// 프론트엔드 린터 설정.
//
// ruff.toml과 같은 방침이다 — 목표는 스타일 통일이 아니라 버그를 잡는 것.
// 스타일 규칙(들여쓰기, 따옴표, 세미콜론)은 켜지 않는다. 이미 일관돼 있고,
// 켜는 순간 손대지 않아도 될 파일 수십 개가 diff에 들어와 정작 중요한
// 변경이 그 안에 묻힌다.
//
// 타입 오류는 이미 `vue-tsc --noEmit`이 빌드마다 잡으므로 여기서 중복하지
// 않는다. ESLint는 타입 검사로 알 수 없는 것만 본다 — v-for에 key가 없다,
// props를 직접 바꾼다, 선언만 하고 안 쓰는 컴포넌트가 있다 같은 것들.
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import pluginVue from "eslint-plugin-vue";

export default [
    {
        ignores: [
            "node_modules/**",
            "static/dist/**",
            // 빌드를 거치지 않고 그대로 서빙하는 관리자 지표 화면 스크립트.
            // 모듈이 아니라 전역 스크립트라 파서 설정이 다르다.
            "static/*.js",
        ],
    },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    ...pluginVue.configs["flat/recommended"],
    {
        files: ["**/*.{js,ts,vue}"],
        languageOptions: {
            globals: { ...globals.browser },
            parserOptions: { parser: tseslint.parser, ecmaVersion: 2022, sourceType: "module" },
        },
        rules: {
            // 스타일 규칙은 전부 끈다.
            "vue/max-attributes-per-line": "off",
            "vue/singleline-html-element-content-newline": "off",
            "vue/html-indent": "off",
            "vue/html-self-closing": "off",
            "vue/attributes-order": "off",
            "vue/first-attribute-linebreak": "off",
            "vue/html-closing-bracket-newline": "off",
            "vue/multiline-html-element-content-newline": "off",

            "vue/html-quotes": "off",
            "vue/html-closing-bracket-spacing": "off",

            // 컴포넌트 파일명이 View/State/Logic 3분할 규약을 따른다.
            // 한 단어(App.vue)도 의도한 것이라 이 규칙은 맞지 않는다.
            "vue/multi-word-component-names": "off",

            // ⚠️ 이 프로젝트의 구조와 정면으로 충돌하는 규칙들이라 끈다.
            //
            // no-mutating-props: View는 State 객체를 prop으로 받아 그 안의 ref를
            //   직접 바꾼다. 그게 View/State/Logic 3분할의 핵심이다. 이 규칙을
            //   켜면 아키텍처 전체가 위반이 된다.
            // require-default-prop: prop을 넘기지 않는 호출 지점이 있는지는
            //   vue-tsc가 타입으로 잡는다. 기본값을 강제하면 "안 넘긴 것"과
            //   "빈 값을 넘긴 것"이 구분되지 않는다.
            // no-explicit-any: 타입 엄격도는 vue-tsc의 영역이다. 여기서 겹쳐
            //   보면 같은 문제를 두 도구가 다른 기준으로 보고하게 된다.
            // no-undef: BufferSource, NotificationPermission 같은 TS 내장 DOM
            //   타입을 ESLint는 모른다. 진짜 미정의 참조는 vue-tsc가 잡는다.
            "vue/no-mutating-props": "off",
            "vue/require-default-prop": "off",
            "@typescript-eslint/no-explicit-any": "off",
            "no-undef": "off",

            // 쓰지 않는 값은 _ 접두사로 의도를 표시할 수 있게 둔다.
            "@typescript-eslint/no-unused-vars": ["error", {
                argsIgnorePattern: "^_",
                varsIgnorePattern: "^_",
                caughtErrorsIgnorePattern: "^_",
            }],
        },
    },
    {
        files: ["tests/**"],
        languageOptions: { globals: { ...globals.browser, ...globals.node } },
    },
];
