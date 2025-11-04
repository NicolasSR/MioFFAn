module.exports = {
  mode: 'production',
  entry: {
    'index': './index.ts',
    'edit_mcdict': './edit_mcdict.ts',
    'compound_concepts_editor': './compound_concepts_editor.ts',
    'equations_of_interest_selector': './equations_of_interest_selector.ts'
  },
  output: {
    filename: '[name].js',
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: 'ts-loader',
      },
    ],
  },
  resolve: {
    extensions: [
      '.ts', '.js',
    ],
  },
};
