module.exports = {
  webpack: {
    plugins: {
      add: [
        function() {
          const webpack = require('webpack');
          return new webpack.HotModuleReplacementPlugin();
        },
      ],
    },
    configure: (webpackConfig, { env, paths }) => {
      if (env === 'development') {
        webpackConfig.devServer = {
          ...webpackConfig.devServer,
          hot: true,
          liveReload: true,
          client: {
            overlay: false,
            logging: 'none',
          },
        };
        // Ensure HMR client script
        webpackConfig.output.hotUpdateChunkFilename = 'static/webpack/[hash].[id].hot-update.js';
      }
      return webpackConfig;
    },
  },
};
