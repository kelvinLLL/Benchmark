# -*- coding: utf-8 -*-
"""
Created on Mon Jul 22 12:16:36 2019

@author: Daniel Lin, Seahymn

"""

import os
import pandas as pd
import datetime
import numpy as np
import matplotlib.pyplot as plt
from keras_preprocessing.sequence import pad_sequences
from keras.callbacks import ModelCheckpoint, EarlyStopping
from keras.callbacks import TensorBoard, CSVLogger
from sklearn.utils import class_weight
from sklearn.metrics import classification_report, confusion_matrix
from keras.models import load_model
from sklearn.model_selection import train_test_split

from src.DataLoader import getCFilesFromText, GenerateLabels, LoadPickleData, SavedPickle, ListToCSV
from src.models.Deep_model import Deep_model
from src.models.textCNN import textCNN

class Helper():
    ''' Super class Solver for all kinds of tasks'''
    def __init__(self, config, paras):
        self.config = config
        self.paras = paras
        self.tokenizer_path = self.config['training_settings']['tokenizer_path']
        self.embed_path = self.config['training_settings']['embedding_model_path']
        self.embed_dim = self.config['model_settings']['model_para']['embedding_dim']
        
        if not os.path.exists(self.paras.data_dir): os.makedirs(self.paras.data_dir)
        if not os.path.exists(self.paras.output_dir): os.makedirs(self.paras.output_dir)
        if not os.path.exists(self.config['training_settings']['model_save_path']): os.makedirs(self.config['training_settings']['model_save_path']) 
        if not os.path.exists(self.paras.logdir): os.makedirs(self.paras.logdir)
    
    def patitionData(self, data_list_pad, data_list_id):
    
        test_size = self.config['training_settings']['dataset_config']['Test_set_ratio']
        validation_size = self.config['training_settings']['dataset_config']['Test_set_ratio'] 
        data_list_label = GenerateLabels(data_list_id)
        
        if not self.config['training_settings']['using_separate_test_set']:
            # The value of the seed for testing should be the same to that was used during the training phase.  
            train_vali_set_x, test_set_x, train_vali_set_y, test_set_y, train_vali_set_id, test_set_id = train_test_split(data_list_pad, data_list_label, data_list_id, test_size=test_size, random_state=self.paras.seed)
            train_set_x, validation_set_x, train_set_y, validation_set_y, train_set_id, validation_set_id = train_test_split(train_vali_set_x, train_vali_set_y, train_vali_set_id, test_size=validation_size, random_state=self.paras.seed)
        
            tuple_with_test = train_set_x, train_set_y, train_set_id, validation_set_x, validation_set_y, validation_set_id, test_set_x, test_set_y, test_set_id
            setattr(self, 'patitioned_data', tuple_with_test)
            return tuple_with_test
        else:
            train_set_x, validation_set_x, train_set_y, validation_set_y, train_set_id, validation_set_id = train_test_split(train_vali_set_x, train_vali_set_y, train_vali_set_id, test_size=validation_size, random_state=self.paras.seed)
            tuple_without_test = train_set_x, train_set_y, train_set_id, validation_set_x, validation_set_y, validation_set_id
            setattr(self, 'patitioned_data', tuple_without_test)
            return tuple_without_test
    
    def verbose(self, msg):
        ''' Verbose function for print information to stdout'''
        if self.paras.verbose == 1:
            print('[INFO]', msg)
            
    def tokenization(self, data_list):
        tokenizer = LoadPickleData(self.tokenizer_path)
        total_sequences = tokenizer.texts_to_sequences(data_list)
        word_index = tokenizer.word_index
        
        return total_sequences, word_index
    
    def padding(self, sequences_to_pad):
        padded_seq = pad_sequences(sequences_to_pad, maxlen = self.config['model_settings']['model_para']['max_sequence_length'], padding ='post')
        return padded_seq
    
    def loadData(self, data_path):
        ''' Load data for training/validation'''
        self.verbose('Loading data from '+ os.getcwd() + os.sep + data_path + '....')
        total_list, total_list_id = getCFilesFromText(data_path)
        self.verbose("The length of the loaded data list is : " + str(len(total_list)))
        return total_list, total_list_id
        
class Trainer(Helper):
    ''' Handler for complete training progress'''
    def __init__(self,config,paras):
        super(Trainer, self).__init__(config,paras)
        self.verbose('Start training process....')
        self.model_save_path = config['training_settings']['model_save_path']
        self.model_save_name = config['training_settings']['model_saved_name']
        self.log_path = config['training_settings']['log_path']
    
    def applyEmbedding(self, w2v_model, word_index):
              
        embeddings_index = {} # a dictionary with mapping of a word i.e. 'int' and its corresponding 100 dimension embedding.

        # Use the loaded model
        for line in w2v_model:
           if not line.isspace():
               values = line.split()
               word = values[0]
               coefs = np.asarray(values[1:], dtype='float32')
               embeddings_index[word] = coefs
        w2v_model.close()
        
        self.verbose('Found %s word vectors.' % len(embeddings_index))
        
        embedding_matrix = np.zeros((len(word_index) + 1, self.embed_dim))
        for word, i in word_index.items():
           embedding_vector = embeddings_index.get(word)
           if embedding_vector is not None:
               # words not found in embedding index will be all-zeros.
               embedding_matrix[i] = embedding_vector
               
        return embedding_matrix
    
    def plot_history(self, network_history): 
        plt.figure()
        plt.xlabel('Epochs')
        plt.ylabel('Loss')
        plt.plot(network_history.history['loss'])
        plt.plot(network_history.history['val_loss'])
        plt.legend(['Training', 'Validation'])
        plt.savefig(self.config['training_settings']['model_save_path'] + os.sep + self.config['training_settings']['model_saved_name'] + '_Epoch_loss' + '.jpg') 
        
    def exec(self):
        
        total_list, total_list_id = self.loadData(self.paras.data_dir)  
        self.verbose("Perform tokenization ....")
        total_sequences, word_index = self.tokenization(total_list)
        self.verbose("Pad the sequence to unified length...")
        total_list_pad = self.padding(total_sequences)
        self.verbose("Patition the data ....")
        data_tuple = self.patitionData(total_list_pad, total_list_id)  
        train_set_x = data_tuple[0] 
        train_set_y = np.asarray(data_tuple[1]).flatten()
        train_set_id = data_tuple[2] 
        validation_set_x = data_tuple[3]
        validation_set_y = np.asarray(data_tuple[4]).flatten()
        validation_set_id = data_tuple[5] 
        #test_set_x = data_tuple[6] 
        #test_set_y = np.asarray(data_tuple[7]).flatten()
        #test_set_id = data_tuple[8]
        
        self.verbose ("-------------------------------------------------------")
        self.verbose ("Data processing completed!")
        self.verbose ("There are " + str(len(train_set_x)) + " total samples in the tr*aining set. " + str(np.count_nonzero(train_set_y)) + " vulnerable samples. " )
        self.verbose ("There are " + str(len(validation_set_x)) + " total samples in the validation set. " + str(np.count_nonzero(validation_set_y)) + " vulnerable samples. " )
        #self.verbose ("There are " + str(len(test_set_x)) + " total samples in the test set. " + str(np.count_nonzero(test_set_y)) + " vulnerable samples. " )
        
        self.verbose ("-------------------------------------------------------")
        self.verbose ("Loading trained Word2vec model. ")
        w2v_model = open(self.embed_path)        
        self.verbose ("The trained word2vec model: ")
        print (w2v_model)
        embedding_matrix = self.applyEmbedding(w2v_model, word_index)
        if self.config['model_settings']['model_para']['handle_data_imbalance']:
            class_weights = class_weight.compute_class_weight(class_weight = 'balanced',classes = np.unique(train_set_y), y = train_set_y)
            print(class_weights)
            class_weights = dict(enumerate(class_weights))
        
        else:
            class_weights = None
        
        self.verbose ("-------------------------------------------------------")
        """
        Initialize the model class here.
        """
        deep_model = Deep_model(self.config)
        test_CNN = textCNN(self.config)
        
        """
        Load the model.
        """
        if self.config['model_settings']['model'] == 'DNN':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = deep_model.build_DNN(word_index, embedding_matrix)
        if self.config['model_settings']['model'] == 'GRU':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = deep_model.build_GRU(word_index, embedding_matrix)
        if self.config['model_settings']['model'] == 'LSTM':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = deep_model.build_LSTM(word_index, embedding_matrix)
        if self.config['model_settings']['model'] == 'BiGRU':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = deep_model.build_BiGRU(word_index, embedding_matrix)
        if self.config['model_settings']['model'] == 'BiLSTM':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = deep_model.build_BiLSTM(word_index, embedding_matrix)
        if self.config['model_settings']['model'] == 'textCNN':
            self.verbose ("Loading the " + self.config['model_settings']['model'] + " model.")
            model_func = test_CNN.buildModel(word_index, embedding_matrix)
        
        self.verbose("Model structure loaded.")
        model_func.summary()
            
        callbacks_list = [
                ModelCheckpoint(filepath = self.config['training_settings']['model_save_path'] + self.config['model_settings']['model'] +
                                '_{epoch:02d}_{val_accuracy:.3f}_{val_loss:3f}' + '.h5', 
                                monitor = self.config['training_settings']['network_config']['validation_metric'], 
                                verbose = self.paras.verbose, 
                                save_best_only = self.config['training_settings']['save_best_model'],
                                save_freq="epoch"),
                                #period = self.config['training_settings']['period_of_saving']),
                EarlyStopping(monitor = self.config['training_settings']['network_config']['validation_metric'], 
                              patience = self.config['training_settings']['network_config']['patcience'], 
                              verbose = self.paras.verbose, 
                              mode="auto"),     
                TensorBoard(log_dir=self.config['training_settings']['log_path'], 
                            batch_size = self.config['training_settings']['network_config']['batch_size'],
                            write_graph=True, 
                            write_grads=True, 
                            write_images=True, 
                            embeddings_freq=0, 
                            embeddings_layer_names=None, 
                            embeddings_metadata=None),
                CSVLogger(self.config['training_settings']['log_path'] + os.sep + self.config['training_settings']['model_saved_name'] + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.log')]
        
        train_history = model_func.fit(train_set_x, train_set_y,
                                       epochs = self.config['training_settings']['network_config']['epochs'],
                                       batch_size = self.config['training_settings']['network_config']['batch_size'],
                                       shuffle = False, # The data has already been shuffle before, so it is unnessary to shuffle it again. (And also, we need to correspond the ids to the features of the samples.))
                                       validation_data = (validation_set_x, validation_set_y),
                                       callbacks = callbacks_list,
                                       verbose=self.paras.verbose, 
                                       class_weight = class_weights)
        if self.config['model_settings']['model'] == 'DNN':
          if self.config['training_settings']['network_config']['save_training_history']:
              SavedPickle(self.config['training_settings']['model_save_path'] + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.pkl', train_history)
        if self.config['training_settings']['network_config']['plot_training_history']:
            self.plot_history(train_history)

class Tester(Helper):
    ''' Handler for complete inference progress'''
    def __init__(self,config,paras):
        super(Tester, self).__init__(config,paras)
        self.verbose('Start testing process....')
        
    def modelLoader(self):
        trained_model_path = self.paras.trained_model
        if os.path.isfile(trained_model_path):
            # Load the model and print the model details.
            trained_model = load_model(trained_model_path)
            trained_model.summary()
            return trained_model
        else:
            self.verbose("Failed to load the trained model!")
            
    def loadTestSet(self):
        if not self.config['training_settings']['using_separate_test_set']:
            total_list, total_list_id = self.loadData(self.paras.data_dir) 
            self.verbose("Perform tokenization ....")
            total_sequences, word_index = self.tokenization(total_list)
            self.verbose("Pad the sequence to unified length...")
            total_list_pad = self.padding(total_sequences)
            self.verbose("Patition the data ....")
            tuple_with_test = self.patitionData(total_list_pad, total_list_id)  
            test_set_x = tuple_with_test[6] 
            test_set_y = np.asarray(tuple_with_test[7]).flatten()
            test_set_id = tuple_with_test[8]
            self.verbose ("There are " + str(len(test_set_x)) + " total samples in the test set. " + str(np.count_nonzero(test_set_y)) + " vulnerable samples. " )
  
        else:
            self.verbose ("Loading test data from " + os.getcwd() + os.sep + self.config['training_settings']['test_set_path'])
            test_list, test_list_id = self.loadData(self.config['training_settings']['test_set_path'])  
            self.verbose("Perform tokenization ....")
            test_sequences, word_index = self.tokenization(test_list)
            self.verbose("Pad the sequence to unified length...")
            test_list_pad = self.padding(test_sequences)
            test_list_label = GenerateLabels(test_list_id)
            test_set_x = test_list_pad
            test_set_y = test_list_label
            
        return test_set_x, test_set_y, test_set_id
    
    def getAccuracy(self, probs, test_set_y):
        predicted_classes = []
        for item in probs:
            if item[0] > 0.5:
                predicted_classes.append(1)
            else:
                predicted_classes.append(0)    
        test_accuracy = np.mean(np.equal(test_set_y, predicted_classes)) 
        return test_accuracy, predicted_classes
    
    
    def exec(self):
        test_set_x, test_set_y, test_set_id = self.loadTestSet()
        model = self.modelLoader()
        probs = model.predict(test_set_x, batch_size = self.config['training_settings']['network_config']['batch_size'], verbose = self.paras.verbose)
        accuracy, predicted_classes = self.getAccuracy(probs, test_set_y)
        self.verbose(self.config['model_settings']['model'] + " classification result: \n")
        self.verbose("Total accuracy: " + str(accuracy))
        self.verbose("----------------------------------------------------")
        self.verbose("The confusion matrix: \n")
        target_names = ["Non-vulnerable","Vulnerable"] #non-vulnerable->0, vulnerable->1
        print (confusion_matrix(test_set_y, predicted_classes, labels=[0,1]))   
        print ("\r\n")
        print (classification_report(test_set_y, predicted_classes, target_names=target_names))
        # Wrap the result to a CSV file.        
        if not isinstance(test_set_x, list): test_set_x = test_set_x.tolist()
        if not isinstance(probs, list): probs = probs.tolist()
        if not isinstance(test_set_id, list): test_set_id = test_set_id.tolist()        
        zippedlist = list(zip(test_set_id, probs, test_set_y))
        result_set = pd.DataFrame(zippedlist, columns = ['Function_ID', 'Probs. of being vulnerable', 'Label'])
        #print(result_set,self.paras.output_dir)
        os.mkdir(self.paras.output_dir + os.sep + self.config['model_settings']['model'])
        ListToCSV(result_set, self.paras.output_dir + os.sep + self.config['model_settings']['model'] + os.sep + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '_result.csv')
          
            
        
        