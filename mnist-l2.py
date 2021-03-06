from __future__ import print_function

import os
import random
import copy

import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn
import torch.optim as optim

from models import FeedForward
from utils import *

# PATHS
CHECKPOINT    = "./checkpoints/mnist-l2"

# BATCH
BATCH_SIZE    = 256
NUM_WORKERS   = 4

# SGD
LEARNING_RATE = 0.01
MOMENTUM      = 0.9
WEIGHT_DECAY  = 1e-4

# Step Decay
LR_DROP       = 0.5
EPOCHS_DROP   = 20

# MISC
EPOCHS        = 100
CUDA          = True

# L2 REGULARIZATION
L2_COEFF = 5e-3

# Manual seed
SEED = 20

random.seed(SEED)
torch.manual_seed(SEED)
if CUDA:
    torch.cuda.manual_seed_all(SEED)

ALL_CLASSES = range(10)

def main():

    if not os.path.isdir(CHECKPOINT):
        os.makedirs(CHECKPOINT)

    print('==> Preparing dataset')

    trainloader, validloader, testloader = load_MNIST(batch_size = BATCH_SIZE, num_workers = NUM_WORKERS)

    print("==> Creating model")
    model = FeedForward(num_classes=len(ALL_CLASSES))

    if CUDA:
        model = model.cuda()
        model = nn.DataParallel(model)
        cudnn.benchmark = True

    print('    Total params: %.2fK' % (sum(p.numel() for p in model.parameters()) / 1000) )

    criterion = nn.BCELoss()
    penalty = None

    CLASSES = []
    AUROCs = []

    for t, cls in enumerate(ALL_CLASSES):

        optimizer = optim.SGD(model.parameters(), 
                lr=LEARNING_RATE, 
                momentum=MOMENTUM, 
                weight_decay=WEIGHT_DECAY
            )

        print('\nTask: [%d | %d]\n' % (t + 1, len(ALL_CLASSES)))

        CLASSES.append(cls)

        print("==> Learning")

        best_loss = 1e10
        learning_rate = LEARNING_RATE

        for epoch in range(EPOCHS):

            # decay learning rate
            if (epoch + 1) % EPOCHS_DROP == 0:
                learning_rate *= LR_DROP
                for param_group in optimizer.param_groups:
                    param_group['lr'] = learning_rate

            print('Epoch: [%d | %d]' % (epoch + 1, EPOCHS))

            train_loss = train(trainloader, model, criterion, ALL_CLASSES, [cls], optimizer = optimizer, penalty = penalty, use_cuda = CUDA)
            test_loss = train(validloader, model, criterion, ALL_CLASSES, [cls], test = True, penalty = penalty, use_cuda = CUDA)

            # save model
            is_best = test_loss < best_loss
            best_loss = min(test_loss, best_loss)
            save_checkpoint({
                'epoch': epoch + 1,
                'state_dict': model.state_dict(),
                'loss': test_loss,
                'optimizer': optimizer.state_dict()
                }, CHECKPOINT, is_best)

        print("==> Calculating AUROC")

        filepath_best = os.path.join(CHECKPOINT, "best.pt")
        checkpoint = torch.load(filepath_best)
        model.load_state_dict(checkpoint['state_dict'])

        auroc = calc_avg_AUROC(model, testloader, ALL_CLASSES, CLASSES, CUDA)

        print( 'AUROC: {}'.format(auroc) )

        AUROCs.append(auroc)

        # create a copy of current model and make the weights fixed
        model_copy = copy.deepcopy(model)
        for param in model_copy.parameters():
            param.requires_grad = False

        # create l2 norm penalty for the next task
        penalty = l2_penalty(model_copy, coeff = L2_COEFF)

    print( '\nAverage Per-task Performance over number of tasks' )
    for i, p in enumerate(AUROCs):
        print("%d: %f" % (i+1,p))

if __name__ == '__main__':
    main()