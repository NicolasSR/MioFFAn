module.exports = {
  mode: 'production',
  entry: {
    'index': './index.ts',
    'edit_mcdict': './edit_mcdict.ts',
    'equations_of_interest_selector': './equations_of_interest_selector.ts',
    'group_creator': './group_creator.ts',
    'nav': './nav.ts',
    'sample_nav': './sample_nav.ts',
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
