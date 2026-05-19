import { createToken, Lexer, CstParser, TokenType, tokenMatcher, IRecognitionException, IToken } from "chevrotain";
import { OperatorInfo } from "./common";

const Identifier = createToken({ name: "Identifier", pattern: /[a-zA-Z_][a-zA-Z0-9_]*/ });
const LParen = createToken({ name: "LParen", pattern: /\(/ });
const RParen = createToken({ name: "RParen", pattern: /\)/ });
const Comma = createToken({ name: "Comma", pattern: /,/ });
const Float   = createToken({name: "Float"   , pattern: /\d+\.\d+/});
const Integer = createToken({name: "Integer" , pattern: /\d+/, longer_alt: Float});
const WhiteSpace = createToken({ name: "WhiteSpace", pattern: /\s+/, group: Lexer.SKIPPED });
const AdditionOperator = createToken({ name: "AdditionOperator", pattern: Lexer.NA });
const Plus = createToken({ name: "Plus", pattern: /\+/, categories: AdditionOperator});
const Minus = createToken({ name: "Minus", pattern: /-/, categories: AdditionOperator});
const MultiplicationOperator = createToken({ name: "MultiplicationOperator", pattern: Lexer.NA });
const Multiply = createToken({ name: "Multiply", pattern: /\*/, categories: MultiplicationOperator});
const Divide = createToken({ name: "Divide", pattern: /\//, categories: MultiplicationOperator});
const Power = createToken({ name: "Power", pattern: /\*\*/ });
const Equal = createToken({ name: "Equal", pattern: /=/ });
const UnaryOperator = createToken({ name: "UnaryOperator", pattern: Lexer.NA });
const BinaryOperator = createToken({ name: "BinaryOperator", pattern: Lexer.NA });

const genericTokens = [
        WhiteSpace,
        Identifier,
        LParen,
        RParen,
        Comma,
        Float,
        Integer,
        Plus,
        Minus,
        Multiply,
        Divide,
        Equal,
        AdditionOperator,
        MultiplicationOperator,
        UnaryOperator,
        BinaryOperator
    ];

let symbolic_code_lexer: Lexer;
let symbolic_code_parser: SymbolicCodeParser;
let symbolic_code_interpreter: any; // we will assign the correct type to this variable after we define the SymbolicCodeInterpreter class.

export function createSymbolicCodeLexer(operators_info_list: OperatorInfo[]) {
    // The list of operators is provided by the server and stored in the `operators_info_list` variable. We need to create tokens for these operators dynamically.

    let unary_operator_tokens = []
    let binary_operator_tokens = []

    for (const operator of operators_info_list) {
        if (operator.arity == 1) {
            unary_operator_tokens.push(createToken({ name: operator.code_token, pattern: new RegExp(`${operator.code_token}`), categories: UnaryOperator }));
        } else if (operator.arity == 2) {
            binary_operator_tokens.push(createToken({ name: operator.code_token, pattern: new RegExp(`${operator.code_token}`), categories: BinaryOperator }));
        } else {
            console.warn(`Unsupported operator arity ${operator.arity} for operator ${operator.operator}. Skipping this operator.`);
        }
    }

    const total_operator_tokens = [...unary_operator_tokens, ...binary_operator_tokens];
    // The list of operator tokens should be ordered by the length of the code_token in descending order to ensure that longer tokens are matched first (e.g., "==" should be matched before "=").
    total_operator_tokens.sort((a, b) => b.name.length - a.name.length);


    symbolic_code_lexer = new Lexer([...total_operator_tokens, ...genericTokens]);

    symbolic_code_parser = new SymbolicCodeParser(unary_operator_tokens, binary_operator_tokens);

    symbolic_code_interpreter = generateInterpreter(symbolic_code_parser);
}


export function tokenizeSymbolicCode(code: string) {
    if (!symbolic_code_lexer) {
        throw new Error("SymbolicCodeLexer is not initialized. Please call createSymbolicCodeLexer with the operator info list before tokenizing.");
    }
    const lexingResult = symbolic_code_lexer.tokenize(code);
    if (lexingResult.errors.length > 0) {
        throw new Error("Lexing errors detected: " + lexingResult.errors[0].message);
    }
    return lexingResult.tokens;
}

function parse(tokenized_code: any, startRuleName: keyof SymbolicCodeParser) {
    if (!symbolic_code_parser) {
        throw new Error("SymbolicCodeParser is not initialized. Please call createSymbolicCodeLexer with the operator info list before evaluating code.");
    }
    symbolic_code_parser.reset();
    symbolic_code_parser.input = tokenized_code;
    const rule = symbolic_code_parser[startRuleName];
    if (typeof rule === "function") {
        const value = rule.call(symbolic_code_parser);
        return { value: value, errors: symbolic_code_parser.errors };
    } else {
        throw new Error(`Start rule "${startRuleName}" does not exist in the parser.`);
    }
}

export function evaluateSymbolicCode(code: string) {
    if (!symbolic_code_interpreter) {
        throw new Error("SymbolicCodeInterpreter is not initialized. Please call createSymbolicCodeLexer with the operator info list before evaluating code.");
    }
    let ast_list = [];
    let total_identifier_token_strings: string[] = [];
    const code_lines = code.split("\n");
    for (const line of code_lines) {
        if (line.trim().length === 0) {
            continue; // skip empty lines
        }
        let tokenized_code = tokenizeSymbolicCode(line);
        let identifier_tokens: IToken[] = tokenized_code;
        let identifier_token_strings: string[];
        identifier_tokens = identifier_tokens.filter(token => tokenMatcher(token, Identifier)); // Match by token type name
        identifier_token_strings = identifier_tokens.map(token => token.image);
        for (const identifier_token_string of identifier_token_strings) {
            if (!total_identifier_token_strings.includes(identifier_token_string)) {
                total_identifier_token_strings.push(identifier_token_string);
            }
        }
        let parseResult = parse(tokenized_code, "assignment_statement");
        if (parseResult.errors.length > 0) {
            throw new Error(parseResult.errors.map((error: IRecognitionException) => error.message).join("\n"));
        }
        let ast = symbolic_code_interpreter.visit(parseResult.value);
        ast_list.push(ast);
    }
    const output = { ast_list: ast_list, identifier_token_strings: total_identifier_token_strings };
    return output;
}

class SymbolicCodeParser extends CstParser {

    public assignment_statement = this.RULE("assignment_statement", () => {
        this.CONSUME(Identifier);
        this.CONSUME(Equal);
        this.SUBRULE(this.expression);
    });

    public expression = this.RULE("expression", () => {
      this.OR([
        { ALT: () => this.SUBRULE(this.unary_minus_expression) },
        { ALT: () => this.SUBRULE(this.addition_expression) }
      ]);
    });

    public unary_minus_expression = this.RULE("unary_minus_expression", () => {
      this.CONSUME(Minus);
      this.SUBRULE(this.expression);
    });

    public addition_expression = this.RULE("addition_expression", () => {
        this.SUBRULE(this.multiplication_expression, { LABEL: "left" });
        this.MANY(() => {
            this.CONSUME(AdditionOperator);
            this.SUBRULE2(this.multiplication_expression, { LABEL: "right" });
        });
    });

    public multiplication_expression = this.RULE("multiplication_expression", () => {
        this.SUBRULE(this.power_expression, { LABEL: "left" });
        this.MANY(() => {
            this.CONSUME(MultiplicationOperator);
            this.SUBRULE2(this.power_expression, { LABEL: "right" });
        });
    });

    public power_expression = this.RULE("power_expression", () => {
        this.SUBRULE(this.atomic_expression, { LABEL: "base" });
        this.OPTION(() => {
            this.CONSUME(Power);
            this.SUBRULE2(this.atomic_expression, { LABEL: "exponent" });
        });
    });
    
    public atomic_expression = this.RULE("atomic_expression", () => 
        this.OR([
            { ALT: () => this.SUBRULE(this.parenthesized_expression) },
            { ALT: () => this.SUBRULE(this.operator_expression)},
            { ALT: () => this.CONSUME(Identifier) },
            { ALT: () => this.SUBRULE(this.number_literal) }
        ])
    );

    public operator_expression = this.RULE("operator_expression", () => {
        this.OR([
            { ALT: () => this.SUBRULE(this.unary_operator_expression) },
            { ALT: () => this.SUBRULE(this.binary_operator_expression) }
        ]);
    });

    public unary_operator_expression = this.RULE("unary_operator_expression", () => {
        this.CONSUME(UnaryOperator, { LABEL: "operator" });
        this.CONSUME(LParen);
        this.SUBRULE(this.expression, { LABEL: "operand" });
        this.CONSUME(RParen);
    });

    public binary_operator_expression = this.RULE("binary_operator_expression", () => {
        this.CONSUME(BinaryOperator, { LABEL: "operator" });
        this.CONSUME(LParen);
        this.SUBRULE(this.expression, { LABEL: "left" });
        this.CONSUME(Comma);
        this.SUBRULE2(this.expression, { LABEL: "right" });
        this.CONSUME(RParen);
    });

    public parenthesized_expression = this.RULE("parenthesized_expression", () => {
      this.CONSUME(LParen);
      this.SUBRULE(this.expression);
      this.CONSUME(RParen);
    });

    public number_literal = this.RULE("number_literal", () =>
        this.OR([
            { ALT: () => this.CONSUME(Float) },
            { ALT: () => this.CONSUME(Integer) }
        ])
    );

    constructor(unary_operator_tokens: TokenType[], binary_operator_tokens: TokenType[]) {
        super([...unary_operator_tokens, ...binary_operator_tokens, ...genericTokens]);
        
        this.performSelfAnalysis();
    }
    
}

function generateInterpreter(parser: SymbolicCodeParser) {
    const symbolic_code_cst_visitor = parser.getBaseCstVisitorConstructor();

    class SymbolicCodeInterpreter extends symbolic_code_cst_visitor {
        constructor() {
            super();
            // This helper will detect any missing or redundant methods on this visitor
            this.validateVisitor();
        }

        assignment_statement(ctx: any) {
            const variableName = ctx.Identifier[0].image;
            const value = this.visit(ctx.expression);
            return { op: "assignment", args: [variableName, value]};
        }

        expression(ctx: any) {
            if (ctx.addition_expression) {
                return this.visit(ctx.addition_expression);
            } else if (ctx.unary_minus_expression) {
                return this.visit(ctx.unary_minus_expression);
            } else {
                throw new Error("Unsupported expression type");
            }
        }

        unary_minus_expression(ctx: any) {
            const operand = this.visit(ctx.expression);
            return { op: "unary_minus", args: [operand] };
        }
        
        addition_expression(ctx: any) {
            let left = this.visit(ctx.left);

            // "rhs" key may be undefined as the grammar defines it as optional (MANY === zero or more).
            if (ctx.right) {
                ctx.right.forEach((right_operand: any, idx: number) => {
                    // there will be one operator for each rhs operand
                    let right = this.visit(right_operand);
                    let operator = ctx.AdditionOperator[idx];
                    if (tokenMatcher(operator, Plus)) {
                    left = { op: "add", args: [left, right] }
                    } else {
                    // Minus
                    left = { op: "subtract", args: [left, right] };
                    }
                });
            }
            return left;
        }

        multiplication_expression(ctx: any) {
            let left = this.visit(ctx.left)
            // "rhs" key may be undefined as the grammar defines it as optional (MANY === zero or more).
            if (ctx.right) {
                ctx.right.forEach((right_operand: any, idx: number) => {
                    // there will be one operator for each rhs operand
                    let right = this.visit(right_operand);
                    let operator = ctx.MultiplicationOperator[idx];
                    if (tokenMatcher(operator, Multiply)) {
                    left = { op: "mult", args: [left, right] }
                    } else {
                    // Divide
                    left = { op: "div", args: [left, right] };
                    }
                });
            }
            return left;
        }

        power_expression(ctx: any) {
            let base = this.visit(ctx.base);
            if (ctx.exponent) {
                let exponent = this.visit(ctx.exponent);
                return { op: "pow", args: [base, exponent] };
            } else {
                return base;
            }
        }

        atomic_expression(ctx: any) {
            if (ctx.parenthesized_expression) {
                return this.visit(ctx.parenthesized_expression);
            } else if (ctx.operator_expression) {
                return this.visit(ctx.operator_expression);
            } else if (ctx.Identifier) {
                return ctx.Identifier[0].image;
            } else if (ctx.number_literal) {
                return this.visit(ctx.number_literal);
            } else {
                throw new Error("Unsupported atomic expression type");
            }
        }

        operator_expression(ctx: any) {
            if (ctx.unary_operator_expression) {
                return this.visit(ctx.unary_operator_expression);
            } else if (ctx.binary_operator_expression) {
                return this.visit(ctx.binary_operator_expression);
            } else {
                throw new Error("Unsupported operator expression type");
            }
        }
        
        unary_operator_expression(ctx: any) {
            const operator_name = ctx.operator[0].image;
            const operand = this.visit(ctx.operand);
            return { op: operator_name, args: [operand] };
        }

        binary_operator_expression(ctx: any) {
            const operator_name = ctx.operator[0].image;
            const left = this.visit(ctx.left);
            const right = this.visit(ctx.right);
            return { op: operator_name, args: [left, right] };
        }

        parenthesized_expression(ctx: any) {
            return this.visit(ctx.expression);
        }

        number_literal(ctx: any) {
            if (ctx.Float) {
                return parseFloat(ctx.Float[0].image);
            } else if (ctx.Integer) {
                return parseInt(ctx.Integer[0].image, 10);
            } else {
                throw new Error("Unsupported number literal type");
            }
        }
    }

    return new SymbolicCodeInterpreter();
}